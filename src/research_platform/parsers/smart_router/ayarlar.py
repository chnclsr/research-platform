"""
Routing thresholds, loaded from one YAML profile and versioned by its contents.

Every number in here changes what the router does, and therefore what text comes
out of a PDF. `acquisition.py` derives `content_hash` from that text, and dedup,
snapshot keys and passage offsets all hang off it -- so a threshold change is a
behaviour change that downstream storage can see.

That is why the version string is DERIVED, never written by hand. `esik_version`
is `<profile name>_<sha256 of the effective settings>`: change a threshold and the
version changes with it, whether or not anyone remembered to. The old hand-edited
constant could drift out of sync with the values it claimed to describe, and
provenance would say the wrong thing without failing.

Two properties this module has to keep:

  * SAFE ABSENCE. No file, unreadable file, broken YAML, missing pyyaml -- all fall
    back to the embedded defaults and record why. A typo in a config file must not
    take the PDF pipeline down.
  * FROZEN PER RUN. Settings are read once at import and never consulted again.
    Nothing here looks at load, queue depth or a budget; see the determinism note
    in engines.py.

What deliberately stays in code, not here: `KRITIK_TETIKLEYICI` / `UYARI` are
diagnosis definitions rather than tunables ("text is actually gone" is a meaning,
not a setting), `priority` is a registry contract, and concurrency/timeout/bridge
belong to deployment (`.env`), not to routing.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Names the YAML profile. Read here and mirrored in `config.py` so a deployment
#: can point at a calibrated profile without editing code.
YOL_ENV = "SMART_ROUTER_CONFIG_PATH"

#: Bumped when the *shape* of the settings changes, not when a value does -- a
#: value change already shows up in the hash.
SEMA_SURUMU = "gate_v2"

# --------------------------------------------------------------------------
# EMBEDDED DEFAULTS — the single source of truth when no profile is supplied.
# These are the values every measurement in the plan was taken with; changing
# one invalidates those numbers, so they are documented in the YAML instead.
# --------------------------------------------------------------------------
VARSAYILAN: Dict[str, Any] = {
    "profil_adi": "gate_v2_kalibre_edilmedi",
    "kapi": {
        "metin": {
            "sayfa_min_karakter": 100,
            "bos_sayfa_karakter": 20,
            "taranmis_kaplama": 0.50,
            "bozuk_karakter_orani": 0.05,
        },
        "tablo": {
            "ortogonal_cizgi": 6,
            # UYGULANDI (2026-08-20): 8 -> 60. Gerekce ve olcum (iki korpus):
            # config/smart_router.yaml, entegrasyon_plani.md Bolum 17.
            "dolu_dikdortgen": 60,
            "izgara_sutun": 3,
            "izgara_satir": 4,
            "izgara_bosluk": 12.0,
            "izgara_y_tolerans": 3.0,
            # UYGULANDI (2026-08-20): kume_kaplama bu esigin ustundeyse
            # (buyuk sekil/diyagram), ortogonal_cizgi tablo sinyaline hic
            # katilmaz. 0.0 = veto kapali.
            "sekil_veto_kaplama": 0.15,
        },
        "sekil": {
            "kume_kaplama": 0.03,
        },
    },
    "yonlendirme": {
        "kalite_esik": 75.0,
        "yuksek_guven_yeter": False,
    },
    "birlestirme": {
        # UYGULANDI (2026-08-20): 0.1, sonra (2026-08-21) 0.1 -> 5.0. YAML
        # profili bozuk/eksikse sistem bu gömülü varsayılana düşüyor
        # (ayarlar.py docstring'i, "SAFE ABSENCE") -- bu yüzden YAML'daki değer
        # ile burası birlikte güncellenmezse, config kaybı sessizce eski
        # davranışa geri döner. `tests/test_parsers.py` bu eşitliği test eder.
        # Gerekçe ve ölçüm: config/smart_router.yaml (karantina karar karnesi:
        # 8 redin 5'i yanlış, r=-0,063, net -0,1943) + rapor O.9/O.11.
        "karantina_tolerans": 5.0,
        # UYGULANDI (2026-08-20): heavy/fast markdown-arindirilmis uzunluk
        # orani bunun altindaysa (fast kullanilabilirken) heavy katastrofik
        # sayilir. Gerekce, olcum ve bilerek yakalanmayan Codex/EUSO vakasi
        # icin config/smart_router.yaml'daki not.
        "icerik_kaybi_esik": 0.20,
        # `smart_pdf._page_scorer` -- the corruption-only comparison the quarantine
        # decision runs on. Kept apart from `critic_ceza` on purpose: that one
        # grades a page, this one compares two engines' versions of one page.
        "corruption": {"gibberish_kat": 100.0, "unicode_ceza": 20.0},
    },
    "critic_ceza": {
        "char_drop": {"esik": 0.10, "kat": 120.0, "tavan": 45.0},
        "gibberish": {"esik": 0.02, "kat": 300.0, "tavan": 25.0},
        # UYGULANDI (2026-08-20) kat 160.0->0.0, SONRA GERI ALINDI (2026-08-20)
        # kat 0.0->160.0: belge-duzeyi dogrulama 5 belgede utility kaybi
        # 0,04-0,20 gosterdi (TWO_COLUMN_CROSS_JUMP+figur deseni). Gerekce:
        # config/smart_router.yaml MIMARI NOT + entegrasyon_plani.md Bolum 17.2i.
        "dangling": {"esik": 0.08, "kat": 160.0, "tavan": 35.0},
        "broken": {"esik": 0.35, "kat": 50.0, "tavan": 15.0},
        # UYGULANDI (2026-08-20): kat 1.5 -> 0.0. Gerekce ve olcum:
        # config/smart_router.yaml MIMARI NOT + entegrasyon_plani.md Bolum 17.
        "hyphen": {"esik": 3.0, "kat": 0.0, "tavan": 15.0},
        "orphan": {"esik": 5.0, "kat": 1.0, "tavan": 10.0},
        "latex": {"kat": 5.0, "tavan": 20.0},
        "tablo_duzensiz": {"esik": 0.15, "kat": 40.0, "tavan": 15.0},
        "baslik_tutarsiz": {"esik": 0.20, "kat": 30.0, "tavan": 10.0},
        "sabit": {"scanned": 60.0, "unicode_bozuk": 10.0},
    },
}


@dataclass(frozen=True)
class Ayarlar:
    """One resolved profile. Immutable: a run must not see it change mid-flight."""

    #: gate.ESIK shape -- flat, because that is what `GirisKapisi` indexes into.
    kapi_esikleri: Dict[str, float]
    #: critic.SAYFA_CEZA shape -- flat, `<metric>_<field>` plus the fixed penalties.
    critic_ceza: Dict[str, float]
    kalite_esik: float
    yuksek_guven_yeter: bool
    #: Heavy text is kept when `heavy >= fast - tolerance`. 0.0 is today's rule.
    karantina_tolerans: float
    #: Below this heavy/fast length ratio (fast usable, markdown stripped),
    #: heavy is catastrophic regardless of the corruption-score comparison.
    icerik_kaybi_esik: float
    #: Coefficients of the corruption-only score the quarantine check compares on.
    corruption: Dict[str, float]
    profil_adi: str
    esik_version: str
    #: Where the values came from, for provenance: a path or "gomulu varsayilan".
    kaynak: str
    #: Anything wrong with the file that was survived rather than raised.
    uyarilar: List[str] = field(default_factory=list)

    def ozet(self) -> Dict[str, Any]:
        """What provenance and health should show about the active profile."""
        return {
            "profil_adi": self.profil_adi,
            "esik_version": self.esik_version,
            "kaynak": self.kaynak,
            "kalite_esik": self.kalite_esik,
            "yuksek_guven_yeter": self.yuksek_guven_yeter,
            "karantina_tolerans": self.karantina_tolerans,
            "uyarilar": list(self.uyarilar),
        }


def varsayilan_yol() -> str:
    """`config/smart_router.yaml` next to the repository root."""
    kok = os.path.abspath(os.path.join(os.path.dirname(__file__), *([os.pardir] * 4)))
    return os.path.join(kok, "config", "smart_router.yaml")


def _ayar_dosyasindan_yol() -> str:
    """`smart_router_config_path` from Settings, so `.env` is honoured too.

    Guarded rather than imported outright: the measurement scripts import this
    package directly, in interpreters that have PyMuPDF but not necessarily
    pydantic-settings. A missing platform config is not an error here, it just
    means the environment variable and the repository default decide.
    """
    try:
        from ...config import get_settings  # noqa: PLC0415
        return (get_settings().smart_router_config_path or "").strip()
    except Exception:
        return ""


def cozulmus_yol(yol: Optional[str] = None) -> str:
    """Explicit argument, then environment, then Settings, then repo default."""
    return (yol or os.environ.get(YOL_ENV) or _ayar_dosyasindan_yol()
            or varsayilan_yol())


def _derin_birlestir(taban: Dict[str, Any], ustu: Dict[str, Any],
                     uyarilar: List[str], onek: str = "") -> Dict[str, Any]:
    """Overlay `ustu` onto `taban`, keeping keys `taban` does not know out.

    An unknown key is a typo far more often than an intent, and silently accepting
    it would mean a profile that looks configured but is not. It is dropped and
    named rather than applied or raised on.
    """
    sonuc = dict(taban)
    for anahtar, deger in (ustu or {}).items():
        tam = f"{onek}{anahtar}"
        if anahtar not in taban:
            uyarilar.append(f"bilinmeyen anahtar yok sayildi: {tam}")
            continue
        if isinstance(taban[anahtar], dict):
            if not isinstance(deger, dict):
                uyarilar.append(f"{tam}: sozluk bekleniyordu, {type(deger).__name__} geldi")
                continue
            sonuc[anahtar] = _derin_birlestir(taban[anahtar], deger, uyarilar, tam + ".")
        else:
            sonuc[anahtar] = deger
    return sonuc


def _dogrula(veri: Dict[str, Any], uyarilar: List[str]) -> Dict[str, Any]:
    """Type- and range-check every leaf, falling back per value rather than wholesale.

    One bad number should cost that number, not the whole profile: the other
    thresholds in the file are still better than the embedded defaults.
    """
    def gez(dugum: Any, taban: Any, yol: str) -> Any:
        if isinstance(taban, dict):
            return {k: gez(dugum.get(k), taban[k], f"{yol}.{k}" if yol else k)
                    for k in taban}
        if isinstance(taban, bool):
            if not isinstance(dugum, bool):
                uyarilar.append(f"{yol}: true/false bekleniyordu, varsayilana donuldu")
                return taban
            return dugum
        if isinstance(taban, (int, float)):
            if isinstance(dugum, bool) or not isinstance(dugum, (int, float)):
                uyarilar.append(f"{yol}: sayi bekleniyordu, varsayilana donuldu")
                return taban
            if dugum < 0:
                uyarilar.append(f"{yol}: negatif deger ({dugum}), varsayilana donuldu")
                return taban
            return dugum
        if isinstance(taban, str):
            if not isinstance(dugum, str) or not dugum.strip():
                uyarilar.append(f"{yol}: metin bekleniyordu, varsayilana donuldu")
                return taban
            return dugum.strip()
        return taban

    return gez(veri, VARSAYILAN, "")


def _surum(etkin: Dict[str, Any]) -> str:
    """`<profile>_<sha8>` over the EFFECTIVE settings, not the file bytes.

    Hashing the merged result means a comment change does not invent a new version,
    and a file that merely restates the defaults gets the same version as no file
    at all -- the version describes behaviour, which is the thing provenance is
    asked about.
    """
    govde = {k: v for k, v in etkin.items() if k != "profil_adi"}
    kanonik = json.dumps(govde, sort_keys=True, separators=(",", ":"), default=str)
    ozet = hashlib.sha256(kanonik.encode("utf-8")).hexdigest()[:8]
    return f"{etkin.get('profil_adi') or SEMA_SURUMU}_{ozet}"


def _duzlestir_kapi(kapi: Dict[str, Any]) -> Dict[str, float]:
    """Nested YAML -> the flat dict `GirisKapisi` already indexes into."""
    duz: Dict[str, float] = {}
    for grup in ("metin", "tablo", "sekil"):
        duz.update(kapi.get(grup) or {})
    return duz


def _duzlestir_ceza(ceza: Dict[str, Any]) -> Dict[str, float]:
    """Nested YAML -> the flat `SAYFA_CEZA` keys (`char_drop_esik`, `scanned`, ...)."""
    duz: Dict[str, float] = {}
    for ad, deger in ceza.items():
        if ad == "sabit":
            duz.update(deger or {})
            continue
        for alan, sayi in (deger or {}).items():
            duz[f"{ad}_{alan}"] = sayi
    return duz


def yukle(yol: Optional[str] = None) -> Ayarlar:
    """Resolve the active profile. Never raises: every failure degrades and is named."""
    uyarilar: List[str] = []
    hedef = cozulmus_yol(yol)
    ham: Dict[str, Any] = {}
    kaynak = "gomulu varsayilan"

    if not os.path.isfile(hedef):
        uyarilar.append(f"profil dosyasi yok, gomulu varsayilanlar kullanildi: {hedef}")
    else:
        try:
            import yaml  # noqa: PLC0415  -- optional at import time, see module docstring
        except ImportError:
            uyarilar.append("pyyaml kurulu degil, gomulu varsayilanlar kullanildi")
        else:
            try:
                with open(hedef, encoding="utf-8") as f:
                    okunan = yaml.safe_load(f)
            except Exception as exc:
                # Deliberately broad. `yaml.YAMLError` descends from Exception and
                # from neither OSError nor ValueError, so a narrower clause here let
                # a malformed profile propagate and take the whole PDF pipeline down
                # -- the one thing this module promises cannot happen. Whatever the
                # loader raises, the answer is the same: use the defaults, say why.
                uyarilar.append(
                    f"profil okunamadi ({type(exc).__name__}), varsayilana donuldu")
            else:
                if okunan is None:
                    uyarilar.append("profil dosyasi bos, gomulu varsayilanlar kullanildi")
                elif not isinstance(okunan, dict):
                    uyarilar.append("profil bir sozluk degil, gomulu varsayilanlar kullanildi")
                else:
                    ham, kaynak = okunan, hedef

    birlesik = _derin_birlestir(VARSAYILAN, ham, uyarilar)
    etkin = _dogrula(birlesik, uyarilar)

    return Ayarlar(
        kapi_esikleri=_duzlestir_kapi(etkin["kapi"]),
        critic_ceza=_duzlestir_ceza(etkin["critic_ceza"]),
        kalite_esik=float(etkin["yonlendirme"]["kalite_esik"]),
        yuksek_guven_yeter=bool(etkin["yonlendirme"]["yuksek_guven_yeter"]),
        karantina_tolerans=float(etkin["birlestirme"]["karantina_tolerans"]),
        icerik_kaybi_esik=float(etkin["birlestirme"]["icerik_kaybi_esik"]),
        corruption=dict(etkin["birlestirme"]["corruption"]),
        profil_adi=str(etkin["profil_adi"]),
        esik_version=_surum(etkin),
        kaynak=kaynak,
        uyarilar=uyarilar,
    )


#: Read once, at import. Callers that need a different profile (calibration
#: sweeps, tests) call `yukle()` themselves and pass the result down explicitly --
#: nothing mutates this one, so a run cannot see it change underneath it.
AYAR = yukle()
