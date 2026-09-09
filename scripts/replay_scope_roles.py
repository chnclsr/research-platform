"""
Kapsam rolünü, kaydedilmiş bir koşunun kararları üzerinde çevrimdışı yeniden oynatır.

NEDEN BU VAR. `01M203HHZXZB61YF59AZZQ2YA4` koşusunda 254 kapsam kararının 121'i
`near_scope` oldu ve kanıt zincirinden düştü; 89'unda bütün zorunlu facet'ler
`matched: true`, dışlama kararları eksiksiz ve hiçbir dışlama eşleşmemişti. Hepsi tek bir
koşuldan düştü: modelin alıntısı kaynak metnin **ham, casefold edilmiş birebir alt dizesi**
değildi. Bu betik, bir düzeltmenin o korpusta ne yapacağını **canlı koşu yapmadan** ölçer:
aynı kayıtlı model çıktısı üç ayrı yüklemden geçirilir.

    stored           koşunun gerçekten kaydettiği rol
    recomputed-old   düzeltme öncesi yüklem (aşağıda DONDURULMUŞ kopyası var)
    recomputed-new   scope_proof.scope_verdict

`recomputed-old` kasten kopyalanmıştır: düzeltme depoya indikten sonra `pipeline`'dan
içe aktarılan bir "eski" yüklem artık eski olmaz ve karşılaştırma sessizce anlamsızlaşır.

KRİTERLER PROTOKOLDEN OKUNUR (`research_runs.protocol->'scope_criteria'`),
`scope_criteria_resolved` olayından değil: o olay onay öncesidir ve bu koşuda round-0 hâli
farklı facet adları (`imaging_modality` / `application_task` / `technology_type`) ve dokuz
dışlama taşıyor. Onaylanan sözleşme protokoldeki hâlidir.

NE ÖLÇMEZ.

  * **Modeli yeniden çalıştırmaz.** Kayıtlı `facet_assessments` / `exclusion_assessments`
    aynen kullanılır. Yalnız yüklemi ölçer, yargıyı değil.
  * **Canlıdan katıdır, bu yüzden ölçtüğü her yükseltme bir ALT SINIRDIR.**
    `ConnectorCandidate.snippet` kalıcı değil; buradaki haystack `title + content[:6000]`,
    canlı koşudakinde ayrıca `snippet` de vardı. Replay'de eşleşen canlıda da eşleşir.
  * **`requested_role` eski koşularda kaydedilmemiştir.** O alan olmadan modelin kendi
    kendine düşürdüğü kaynaklar sayılamaz; bu yüzden her iki tarafa da aynı şerit
    (`--assume-role`, varsayılan `primary_in_scope`) verilir. Yeni koşularda alan
    `source_decision` olayının üst düzeyinde bulunur ve varsa o kullanılır.
  * **Kaynak hijyenini ölçmez.** Yükselen bir kaynağın liste sayfası mı gerçek bir makale
    mi olduğu edinim katmanının sorunudur; `--show` çıktısı gözle denetlenmek içindir.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from research_platform.schemas import ResearchScopeCriteria, SourceScopeRole
from research_platform.scope_proof import exclusion_decision, scope_verdict

VARSAYILAN_KONTEYNER = "research-platform-postgres-1"

# Satır formatı: ev betiğinin `-tAF $'\x1f'` + splitlines() kalıbı burada veriyi bozar,
# çünkü `content` satır sonu taşır. `row_to_json` Postgres tarafında kaçırır.
SORGU = """
select row_to_json(t)::text from (
  select e.payload->>'source_id'          as source_id,
         e.payload->>'source_version_id'  as source_version_id,
         e.payload->>'role'               as stored_role,
         e.payload->>'requested_role'     as requested_role,
         e.payload->>'title'              as title,
         e.payload->'scope_assessment'    as scope_assessment,
         coalesce(s.title, '')            as sv_title,
         left(coalesce(sv.content, ''), 6000) as content
  from run_events e
  left join source_versions sv on sv.id = e.payload->>'source_version_id'
  left join sources s on s.id = sv.source_id
  where e.run_id = '{run_id}' and e.event_type = 'source_decision'
) t;
"""

PROTOKOL_SORGU = """
select row_to_json(t)::text from (
  select protocol->'scope_criteria' as scope_criteria
  from research_runs where id = '{run_id}'
) t;
"""


def _psql(konteyner: str, sorgu: str) -> list[dict[str, Any]]:
    c = subprocess.run(
        ["docker", "exec", konteyner, "psql", "-U", "research", "-d", "research",
         "-tA", "-c", sorgu],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if c.returncode != 0:
        raise RuntimeError(f"psql basarisiz: {c.stderr.strip()[:300]}")
    return [json.loads(s) for s in c.stdout.splitlines() if s.strip()]


def _eski_yuklem(
    criteria: ResearchScopeCriteria,
    requested_role: SourceScopeRole,
    facet_assessments: list[dict[str, Any]],
    exclusion_assessments: list[dict[str, Any]],
    assessment_text: str,
    classification_reason: str,
) -> SourceScopeRole:
    """`pipeline._validated_scope_role`'un düzeltme ÖNCESİ hâlinin dondurulmuş kopyası.

    Bilerek kopyalandı: içe aktarılsaydı düzeltme indikten sonra "eski taraf" da yeni
    davranışı gösterir ve bu betiğin bütün karşılaştırması sessizce yalan söylerdi.
    """
    haystack = assessment_text.casefold()
    facet_by_name = {
        str(item.get("facet") or ""): item
        for item in facet_assessments
        if str(item.get("facet") or "")
    }
    exclusion_by_signal = {
        signal: exclusion_decision(signal, exclusion_assessments, criteria.exclusion_signals)
        for signal in criteria.exclusion_signals
    }
    if not str(classification_reason or "").strip():
        return SourceScopeRole.NEAR_SCOPE

    exclusion_decisions_complete = all(
        (item := exclusion_by_signal.get(signal)) is not None
        and isinstance(item.get("matched"), bool)
        and bool(str(item.get("reason") or "").strip())
        for signal in criteria.exclusion_signals
    )
    for signal in criteria.exclusion_signals:
        item = exclusion_by_signal.get(signal)
        if (
            not item
            or item.get("matched") is not True
            or not str(item.get("reason") or "").strip()
        ):
            continue
        evidence = str(item.get("evidence") or "").strip().casefold()
        if evidence and evidence in haystack:
            return SourceScopeRole.EXCLUDED
        return SourceScopeRole.NEAR_SCOPE

    if requested_role == SourceScopeRole.EXCLUDED:
        return SourceScopeRole.NEAR_SCOPE
    if requested_role not in {
        SourceScopeRole.PRIMARY_IN_SCOPE,
        SourceScopeRole.SUPPORTING_BENCHMARK,
    }:
        return requested_role
    all_facets = {facet.name for facet in criteria.required_facets}
    facet_decisions_complete = all(
        name in facet_by_name
        and isinstance(facet_by_name[name].get("matched"), bool)
        and bool(str(facet_by_name[name].get("reason") or "").strip())
        for name in all_facets
    )
    required = set(all_facets)
    if requested_role == SourceScopeRole.SUPPORTING_BENCHMARK:
        required.discard("task")
    proven = {
        name
        for name, item in facet_by_name.items()
        if item.get("matched") is True
        and (evidence := str(item.get("evidence") or "").strip().casefold())
        and evidence in haystack
    }
    if (
        not facet_decisions_complete
        or not required.issubset(proven)
        or not exclusion_decisions_complete
    ):
        return SourceScopeRole.NEAR_SCOPE
    return requested_role


def _serit(karar: dict[str, Any], varsayilan: SourceScopeRole) -> SourceScopeRole:
    """Bu kararın hangi şeritte değerlendirileceği (`requested_role`).

    Yeni koşularda alan doğrudan kayıtlıdır. Eskilerde değil -- ama kısmen **çıkarılabilir**:
    düzeltme öncesi yüklem `primary_in_scope` ya da `supporting_benchmark` rolünü YALNIZCA
    o rol istendiğinde döndürür (istenmeyen her şey `near_scope`'a düşer). Dolayısıyla
    kaydedilmiş rol bu ikisinden biriyse istenen rol tam olarak odur.

    `near_scope` ve `excluded` için çıkarım yapılamaz -- ikisi de düşürme sonucu olabilir --
    ve orada `--assume-role` devreye girer. Şeridi elle sabitlemek `supporting_benchmark`
    kaynaklarının benchmark muafiyetini kapatır ve yükseltmeleri olduğundan az gösterir.
    """
    if karar.get("requested_role"):
        return SourceScopeRole(karar["requested_role"])
    stored = str(karar.get("stored_role") or "")
    if stored in {
        SourceScopeRole.PRIMARY_IN_SCOPE.value,
        SourceScopeRole.SUPPORTING_BENCHMARK.value,
    }:
        return SourceScopeRole(stored)
    return varsayilan


def _dagilim(roller: list[str]) -> str:
    sayac = Counter(roller)
    return "  ".join(f"{ad} {n}" for ad, n in sorted(sayac.items(), key=lambda kv: -kv[1]))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--container", default=VARSAYILAN_KONTEYNER)
    ap.add_argument(
        "--assume-role",
        default=SourceScopeRole.PRIMARY_IN_SCOPE.value,
        choices=[r.value for r in SourceScopeRole],
        help="requested_role kaydedilmemis ve kayitli rolden cikarilamayan kararlarda "
             "her iki tarafa verilen serit",
    )
    ap.add_argument("--show", type=int, default=0, metavar="N",
                    help="yukseltilen kaynaklardan N tanesini baslik ve rotalariyla listele")
    ap.add_argument("--out", default="", help="ayrintili sonucu bu JSON dosyasina yaz")
    args = ap.parse_args()

    protokol = _psql(args.container, PROTOKOL_SORGU.format(run_id=args.run_id))
    if not protokol or not protokol[0].get("scope_criteria"):
        print(f"{args.run_id}: protokolde onaylanmis scope_criteria yok")
        return 1
    criteria = ResearchScopeCriteria.model_validate(protokol[0]["scope_criteria"])

    kararlar = _psql(args.container, SORGU.format(run_id=args.run_id))
    if not kararlar:
        print(f"{args.run_id}: source_decision olayi bulunamadi")
        return 1

    varsayilan = SourceScopeRole(args.assume_role)
    stored: list[str] = []
    eski: list[str] = []
    yeni: list[str] = []
    gecisler: Counter[str] = Counter()
    yuklem_gecisleri: Counter[str] = Counter()
    gerilemeler: list[dict[str, Any]] = []
    rota_histogram: dict[str, Counter[str]] = {}
    quote_only = 0
    yukselenler: list[dict[str, Any]] = []
    eksik_icerik = 0

    for karar in kararlar:
        assessment = karar.get("scope_assessment") or {}
        facets = assessment.get("facet_assessments") or []
        exclusions = assessment.get("exclusion_assessments") or []
        reason = str(assessment.get("reason") or "")
        # Canlı koşuda ayrıca `candidate.snippet` de vardı; o kalıcı değil, dolayısıyla
        # buradaki haystack canlıdan dar ve bu ölçüm bir alt sınır.
        # Canli kosuda haystack `candidate.title` ile baslar; kalici karsiligi
        # `sources.title`. `source_versions` baslik tasimaz.
        metin = " ".join([karar.get("sv_title") or "", karar.get("content") or ""])
        if not (karar.get("content") or "").strip():
            eksik_icerik += 1
        istenen = _serit(karar, varsayilan)

        stored_role = str(karar.get("stored_role") or "")
        eski_rol = _eski_yuklem(criteria, istenen, facets, exclusions, metin, reason)
        verdict = scope_verdict(criteria, istenen, facets, exclusions, metin, reason)

        stored.append(stored_role)
        eski.append(eski_rol.value)
        yeni.append(verdict.role.value)
        if stored_role and stored_role != verdict.role.value:
            gecisler[f"{stored_role} -> {verdict.role.value}"] += 1
        if eski_rol != verdict.role:
            yuklem_gecisleri[f"{eski_rol.value} -> {verdict.role.value}"] += 1
        kanita_uygun = {
            SourceScopeRole.PRIMARY_IN_SCOPE,
            SourceScopeRole.SUPPORTING_BENCHMARK,
        }
        if eski_rol in kanita_uygun and verdict.role not in kanita_uygun:
            gerilemeler.append({
                "title": karar.get("title") or karar.get("sv_title") or "",
                "eski": eski_rol.value,
                "yeni": verdict.role.value,
                "gerekceler": list(verdict.reasons),
            })

        rotalar = rota_histogram.setdefault(verdict.role.value, Counter())
        for proof in verdict.facet_proofs:
            rotalar[proof.route] += 1

        yukseldi = (
            stored_role in {SourceScopeRole.NEAR_SCOPE.value, SourceScopeRole.EXCLUDED.value}
            and verdict.role.value in {
                SourceScopeRole.PRIMARY_IN_SCOPE.value,
                SourceScopeRole.SUPPORTING_BENCHMARK.value,
            }
        )
        if yukseldi:
            # Yalnız alıntıyla yükselenler: hiçbir facet'inde kabul edilen değer metinde
            # yok. Bu, yüklemin fazla gevşediğini ele veren sınıftır -- kırık tespiti.
            yalnizca_alinti = bool(verdict.facet_proofs) and all(
                not proof.value_present for proof in verdict.facet_proofs
            )
            quote_only += yalnizca_alinti
            yukselenler.append({
                "title": karar.get("title") or karar.get("sv_title") or "",
                "stored": stored_role,
                "yeni": verdict.role.value,
                "quote_only": yalnizca_alinti,
                "rotalar": {p.facet: p.route for p in verdict.facet_proofs},
            })

    print(f"{args.run_id}  ·  {len(kararlar)} karar  ·  "
          f"{len(criteria.required_facets)} zorunlu facet, "
          f"{len(criteria.exclusion_signals)} dislama")
    if eksik_icerik:
        print(f"UYARI: {eksik_icerik} kararin source_versions icerigi bos; "
              f"bunlar replay'de kacinilmaz olarak near kalir")
    print()
    print(f"  stored          {_dagilim(stored)}")
    print(f"  recomputed-old  {_dagilim(eski)}")
    print(f"  recomputed-new  {_dagilim(yeni)}")
    print()

    # KABUL KAPISI. Yalnız yüklem değişiyor: aynı girdi, aynı şerit. `stored` tarafı
    # buna karışmaz, çünkü replay canlıdan katı (`snippet` kalıcı değil) ve oradaki her
    # fark düzeltmenin degil eksik metnin sonucudur.
    print("recomputed-old -> recomputed-new  (yalniz yuklem farki)")
    if not yuklem_gecisleri:
        print("  (gecis yok)")
    for gecis, n in yuklem_gecisleri.most_common():
        print(f"  {n:>4}  {gecis}")
    print(f"  GERILEME: {len(gerilemeler)} "
          f"(eskiden kanita uygun, yeni yuklemde degil -- sifir olmali)")
    for kayit in gerilemeler[:10]:
        print(f"      {kayit['eski']} -> {kayit['yeni']}  {kayit['title'][:80]}")
        print(f"        {kayit['gerekceler']}")
    print()

    print("stored -> recomputed-new  (yuklem + replay katiligi birlikte)")
    if not gecisler:
        print("  (gecis yok)")
    for gecis, n in gecisler.most_common():
        print(f"  {n:>4}  {gecis}")
    print()

    print("rol basina facet kanit rotasi")
    for rol, sayac in sorted(rota_histogram.items()):
        # EXCLUDED dışlamada kısa devre yapar, facet'lere hiç bakmaz.
        dokum = "  ".join(f"{ad} {n}" for ad, n in sayac.most_common())
        print(f"  {rol:<22}{dokum or '(facet degerlendirilmedi)'}")
    print()
    print(f"yukselen kaynak: {len(yukselenler)}  ·  "
          f"bunlarin {quote_only} tanesi YALNIZ alintiyla "
          f"(hicbir facet'inde kabul edilen deger metinde yok)")

    if args.show and yukselenler:
        print()
        print(f"yukselenlerden ilk {args.show}:")
        for kayit in yukselenler[: args.show]:
            isaret = " [yalniz-alinti]" if kayit["quote_only"] else ""
            print(f"  {kayit['stored']} -> {kayit['yeni']}{isaret}  {kayit['title'][:90]}")
            print(f"      {kayit['rotalar']}")

    if args.out:
        hedef = Path(args.out)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(json.dumps({
            "schema": "scope-role-replay/1",
            "run_id": args.run_id,
            "assume_role": args.assume_role,
            "karar_sayisi": len(kararlar),
            "dagilim": {
                "stored": dict(Counter(stored)),
                "recomputed_old": dict(Counter(eski)),
                "recomputed_new": dict(Counter(yeni)),
            },
            "gecisler": dict(gecisler),
            "yuklem_gecisleri": dict(yuklem_gecisleri),
            "gerilemeler": gerilemeler,
            "rota_histogram": {k: dict(v) for k, v in rota_histogram.items()},
            "quote_only": quote_only,
            "yukselenler": yukselenler,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nyazildi: {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
