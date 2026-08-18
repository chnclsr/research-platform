"""``research-admin`` -- account administration from the shell.

There is no self-service registration: the panel has no sign-up form, so the first
admin has to come from somewhere outside the web surface. That is this command.

Run it wherever ``DATABASE_URL`` points at the platform database -- on this workstation
that means either the host ``.venv`` or ``docker compose exec api``.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from .db import ApiKeyRow, ResearchRunRow, SessionLocal, TelegramIdentityRow, UserRow
from .identity import (
    IdentityError,
    create_user,
    get_user_by_email,
    issue_api_key,
    link_telegram,
    set_password,
)


def _prompt_password(confirm: bool = True) -> str:
    """Read a password without echoing it, so it stays out of shell history."""
    password = getpass.getpass("Parola: ")
    if not password:
        raise SystemExit("Parola bos olamaz")
    if confirm and getpass.getpass("Parola (tekrar): ") != password:
        raise SystemExit("Parolalar eslesmiyor")
    return password


async def _bootstrap(args: argparse.Namespace) -> int:
    """Create the first admin and hand it every run that predates ownership.

    Refuses to run once any account exists: a second call would otherwise be a way to
    mint an admin on a live system.
    """
    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count()).select_from(UserRow))
        if existing:
            print(
                f"Bootstrap reddedildi: {existing} hesap zaten var. "
                "Yeni yonetici icin 'create-user --role admin' kullan.",
                file=sys.stderr,
            )
            return 1
        password = args.password or _prompt_password()
        user = await create_user(
            session,
            email=args.email,
            display_name=args.display_name or args.email,
            password=password,
            role="admin",
        )
        orphaned = await session.execute(
            update(ResearchRunRow)
            .where(ResearchRunRow.owner_id.is_(None))
            .values(owner_id=user.id)
        )
        await session.commit()
        print(f"Yonetici olusturuldu: {user.email} ({user.id})")
        print(f"Sahipsiz kosu devredildi: {orphaned.rowcount}")
    return 0


async def _create_user(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        password = args.password or _prompt_password()
        user = await create_user(
            session,
            email=args.email,
            display_name=args.display_name or args.email,
            password=password,
            role=args.role,
        )
        print(f"Olusturuldu: {user.email} ({user.id}) rol={user.role}")
    return 0


async def _list_users(_: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        users = list(await session.scalars(select(UserRow).order_by(UserRow.created_at)))
        if not users:
            print("Hic hesap yok. Once 'research-admin bootstrap' calistir.")
            return 0
        counts = dict(
            (
                await session.execute(
                    select(ResearchRunRow.owner_id, func.count()).group_by(ResearchRunRow.owner_id)
                )
            ).all()
        )
        width = max(len(user.email) for user in users)
        print(f"{'E-POSTA'.ljust(width)}  {'ROL':<6} {'DURUM':<6} {'KOSU':>5}  ID")
        for user in users:
            state = "aktif" if user.is_active else "kapali"
            print(
                f"{user.email.ljust(width)}  {user.role:<6} {state:<6} "
                f"{counts.get(user.id, 0):>5}  {user.id}"
            )
        orphans = counts.get(None, 0)
        if orphans:
            print(f"\nSahipsiz kosu: {orphans} (yalniz yoneticiler gorebilir)")
    return 0


async def _set_password(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        user = await get_user_by_email(session, args.email)
        if user is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        await set_password(session, user, args.password or _prompt_password())
        print(f"Parola guncellendi: {user.email}. Acik oturumlari dusuruldu.")
    return 0


async def _set_role(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        user = await get_user_by_email(session, args.email)
        if user is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        user.role = args.role
        await session.commit()
        print(f"{user.email} rolu: {user.role}")
    return 0


async def _set_active(args: argparse.Namespace, active: bool) -> int:
    async with SessionLocal() as session:
        user = await get_user_by_email(session, args.email)
        if user is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        if not active and user.role == "admin":
            admins = await session.scalar(
                select(func.count())
                .select_from(UserRow)
                .where(UserRow.role == "admin", UserRow.is_active.is_(True))
            )
            if admins <= 1:
                print(
                    "Reddedildi: bu son aktif yonetici. Once baska bir yonetici ata.",
                    file=sys.stderr,
                )
                return 1
        user.is_active = active
        # Deactivation has to drop live sessions too, or the account stays usable
        # until its cookie happens to expire.
        if not active:
            user.token_version += 1
        await session.commit()
        print(f"{user.email}: {'aktif' if active else 'kapali'}")
    return 0


async def _issue_key(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        user = await get_user_by_email(session, args.email)
        if user is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        full_key, row = await issue_api_key(session, user_id=user.id, name=args.name)
        print(f"Anahtar '{row.name}' olusturuldu ({user.email}).")
        print("Bu deger bir daha gosterilmeyecek:\n")
        print(f"  {full_key}\n")
    return 0


async def _list_keys(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        query = select(ApiKeyRow, UserRow).where(ApiKeyRow.user_id == UserRow.id)
        if args.email:
            user = await get_user_by_email(session, args.email)
            if user is None:
                print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
                return 1
            query = query.where(ApiKeyRow.user_id == user.id)
        rows = (await session.execute(query.order_by(ApiKeyRow.created_at))).all()
        if not rows:
            print("Anahtar yok.")
            return 0
        for key, user in rows:
            state = "iptal" if key.revoked_at else "aktif"
            used = key.last_used_at.strftime("%Y-%m-%d") if key.last_used_at else "hic"
            print(f"{key.id}  {user.email:<28} {key.name:<20} {state:<6} son kullanim={used}")
    return 0


async def _revoke_key(args: argparse.Namespace) -> int:
    """Revoke a key from the shell.

    The panel can do this too, but a leaked key needs a path that does not depend on
    being able to sign in -- and an administrator has to be able to revoke a key that
    is not their own.
    """
    async with SessionLocal() as session:
        row = await session.get(ApiKeyRow, args.key_id)
        if row is None:
            print(f"Anahtar bulunamadi: {args.key_id}", file=sys.stderr)
            return 1
        if row.revoked_at is not None:
            print("Bu anahtar zaten iptal edilmis.")
            return 0
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()
        print(f"Anahtar iptal edildi: {args.key_id}")
    return 0


async def _link_telegram(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        user = await get_user_by_email(session, args.email)
        if user is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        await link_telegram(session, telegram_user_id=args.telegram_id, user_id=user.id)
        print(f"Telegram {args.telegram_id} -> {user.email}")
    return 0


async def _list_telegram(_: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(TelegramIdentityRow, UserRow).where(TelegramIdentityRow.user_id == UserRow.id)
            )
        ).all()
        if not rows:
            print("Eslenmiş Telegram hesabi yok.")
            return 0
        for identity, user in rows:
            print(f"{identity.telegram_user_id:<15} {user.email}")
    return 0


async def _assign_runs(args: argparse.Namespace) -> int:
    """Move runs to an owner -- for orphans, or after someone leaves."""
    async with SessionLocal() as session:
        target = await get_user_by_email(session, args.email)
        if target is None:
            print(f"Kullanici bulunamadi: {args.email}", file=sys.stderr)
            return 1
        statement = update(ResearchRunRow).values(owner_id=target.id)
        if args.run_id:
            statement = statement.where(ResearchRunRow.id.in_(args.run_id))
        elif args.orphaned:
            statement = statement.where(ResearchRunRow.owner_id.is_(None))
        elif args.from_email:
            source = await get_user_by_email(session, args.from_email)
            if source is None:
                print(f"Kaynak kullanici bulunamadi: {args.from_email}", file=sys.stderr)
                return 1
            statement = statement.where(ResearchRunRow.owner_id == source.id)
        else:
            print(
                "Bir secim belirt: --run-id, --orphaned ya da --from-email.",
                file=sys.stderr,
            )
            return 1
        result = await session.execute(statement)
        await session.commit()
        print(f"{result.rowcount} kosu {target.email} hesabina tasindi.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-admin",
        description="Research Platform hesap yonetimi",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def with_password(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--password",
            help="Belirtilmezse sorulur. Kabuk gecmisine dusmemesi icin tercih edilen yol sormaktir.",
        )

    bootstrap = sub.add_parser("bootstrap", help="Ilk yoneticiyi olustur ve mevcut kosulari devret")
    bootstrap.add_argument("email")
    bootstrap.add_argument("--display-name")
    with_password(bootstrap)
    bootstrap.set_defaults(handler=_bootstrap)

    create = sub.add_parser("create-user", help="Yeni hesap olustur")
    create.add_argument("email")
    create.add_argument("--display-name")
    create.add_argument("--role", choices=["user", "admin"], default="user")
    with_password(create)
    create.set_defaults(handler=_create_user)

    listing = sub.add_parser("list-users", help="Hesaplari ve kosu sayilarini listele")
    listing.set_defaults(handler=_list_users)

    password = sub.add_parser("set-password", help="Parola degistir ve oturumlari dusur")
    password.add_argument("email")
    with_password(password)
    password.set_defaults(handler=_set_password)

    role = sub.add_parser("set-role", help="Rol ata")
    role.add_argument("email")
    role.add_argument("role", choices=["user", "admin"])
    role.set_defaults(handler=_set_role)

    activate = sub.add_parser("activate", help="Hesabi yeniden ac")
    activate.add_argument("email")
    activate.set_defaults(handler=lambda args: _set_active(args, True))

    deactivate = sub.add_parser("deactivate", help="Hesabi kapat ve oturumlarini dusur")
    deactivate.add_argument("email")
    deactivate.set_defaults(handler=lambda args: _set_active(args, False))

    issue = sub.add_parser("issue-key", help="Kullanici icin API anahtari uret")
    issue.add_argument("email")
    issue.add_argument("--name", default="cli", help="Anahtari tanimlayan etiket")
    issue.set_defaults(handler=_issue_key)

    keys = sub.add_parser("list-keys", help="API anahtarlarini listele")
    keys.add_argument("--email", help="Tek kullaniciyla sinirla")
    keys.set_defaults(handler=_list_keys)

    revoke = sub.add_parser("revoke-key", help="API anahtarini iptal et")
    revoke.add_argument("key_id", help="list-keys ciktisindaki anahtar kimligi")
    revoke.set_defaults(handler=_revoke_key)

    telegram = sub.add_parser("link-telegram", help="Telegram hesabini kullaniciya bagla")
    telegram.add_argument("email")
    telegram.add_argument("telegram_id", type=int)
    telegram.set_defaults(handler=_link_telegram)

    telegram_list = sub.add_parser("list-telegram", help="Telegram eslemelerini listele")
    telegram_list.set_defaults(handler=_list_telegram)

    assign = sub.add_parser("assign-runs", help="Kosularin sahibini degistir")
    assign.add_argument("email", help="Hedef kullanici")
    assign.add_argument("--run-id", action="append", help="Belirli kosu (tekrarlanabilir)")
    assign.add_argument("--orphaned", action="store_true", help="Sahipsiz kosularin tumu")
    assign.add_argument("--from-email", help="Bu kullanicinin tum kosulari")
    assign.set_defaults(handler=_assign_runs)

    return parser


def run() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(asyncio.run(args.handler(args)))
    except IdentityError as exc:
        raise SystemExit(f"Hata: {exc}") from exc
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    run()
