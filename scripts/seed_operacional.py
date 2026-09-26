import asyncio
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

from app.config import settings

PREFIXO = "seed_"
ESQUEMA = Path(__file__).with_name("esquema_go_local.sql")
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "db", "nutriz-ia-db"}

ETAPAS = (
    "Exame de sangue",
    "Entregar kit de ordenha",
    "Coletar leite",
    "Análise de leite",
)

REGIOES = (
    ("Sao Paulo", "Pinheiros"), ("Sao Paulo", "Moema"), ("Sao Paulo", "Tatuape"),
    ("Sao Paulo", "Santana"), ("Sao Paulo", "Vila Mariana"), ("Sao Paulo", "Butanta"),
    ("Osasco", "Centro"), ("Osasco", "Jardim das Flores"), ("Itapevi", "Centro"),
    ("Barueri", "Alphaville"), ("Carapicuiba", "Vila Dirce"), ("Cotia", "Granja Viana"),
)

NOMES = (
    "Beatriz Souza", "Camila Rocha", "Daniela Lima", "Fernanda Alves", "Gabriela Costa",
    "Helena Martins", "Isabela Ferreira", "Juliana Ribeiro", "Larissa Gomes", "Mariana Dias",
    "Natalia Barros", "Patricia Moreira", "Renata Cardoso", "Sabrina Teixeira", "Tatiane Nunes",
    "Vanessa Pinto", "Aline Castro", "Bruna Freitas", "Carolina Mendes", "Debora Azevedo",
    "Eduarda Ramos", "Flavia Lopes", "Giovana Duarte", "Isadora Vieira", "Jessica Monteiro",
    "Karina Batista", "Leticia Farias", "Luana Correia", "Marcela Pires", "Nicole Araujo",
    "Paula Cavalcanti", "Rafaela Melo", "Simone Rezende", "Thais Campos", "Viviane Xavier",
    "Yasmin Queiroz",
)
MOTORISTAS = ("Carlos Andrade", "Marta Figueiredo", "Joao Pereira", "Rogerio Salles")
ENFERMAGEM = ("Ana Oliveira", "Bianca Torres", "Claudia Nogueira")


def _agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _url_do_banco() -> str:
    return settings.database_url.replace("+asyncpg", "")


def _garantir_banco_local() -> None:
    host = urlparse(_url_do_banco()).hostname
    if host not in HOSTS_LOCAIS:
        raise SystemExit(f"Seed recusado: o banco '{host}' nao e local.")


async def _limpar(conn: asyncpg.Connection) -> None:
    padrao = f"{PREFIXO}%"
    await conn.execute("DELETE FROM job WHERE id_job LIKE $1", padrao)
    await conn.execute(
        "DELETE FROM route_donation_step WHERE id_route_donation_step LIKE $1", padrao
    )
    await conn.execute("DELETE FROM route WHERE id_route LIKE $1", padrao)
    await conn.execute("DELETE FROM bottle WHERE id_bottle LIKE $1", padrao)
    await conn.execute("DELETE FROM donation_step WHERE id_donation_step LIKE $1", padrao)
    await conn.execute("DELETE FROM donation WHERE id_donation LIKE $1", padrao)
    await conn.execute("DELETE FROM address WHERE id_address LIKE $1", padrao)
    await conn.execute('DELETE FROM "user" WHERE id_user LIKE $1', padrao)


async def _usuario(
    conn: asyncpg.Connection,
    id_user: str,
    tipo: str,
    nome: str,
    indice: int,
    exame: datetime | None = None,
) -> None:
    agora = _agora()
    await conn.execute(
        'INSERT INTO "user" (id_user, type, name, cpf, birth_date, phone_number, email, '
        "password, created_at, created_by, blood_exam_valid_until) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, 'seed', $8, $1, $9)",
        id_user,
        tipo,
        nome,
        f"{90000000000 + indice:011d}",
        agora - timedelta(days=365 * 29),
        f"1198{indice:07d}",
        f"{id_user}@seed.nutriz",
        agora - timedelta(days=random.randint(20, 120)),
        exame,
    )


async def _equipe(conn: asyncpg.Connection) -> tuple[list[str], list[str]]:
    motoristas = []
    for i, nome in enumerate(MOTORISTAS):
        id_user = f"{PREFIXO}mot_{i}"
        await _usuario(conn, id_user, "driver", nome, 100 + i)
        motoristas.append(id_user)

    enfermeiras = []
    for i, nome in enumerate(ENFERMAGEM):
        id_user = f"{PREFIXO}enf_{i}"
        await _usuario(conn, id_user, "nurse", nome, 200 + i)
        enfermeiras.append(id_user)

    return motoristas, enfermeiras


async def _doadoras(
    conn: asyncpg.Connection, enfermeiras: list[str]
) -> dict[tuple[str, str], list[str]]:
    agora = _agora()
    etapas_por_regiao: dict[tuple[str, str], list[str]] = {}

    for i, nome in enumerate(NOMES):
        id_user = f"{PREFIXO}doa_{i}"
        cidade, bairro = REGIOES[i % len(REGIOES)]
        await _usuario(
            conn, id_user, "common", nome, 300 + i,
            agora + timedelta(days=random.randint(-20, 170)),
        )
        await conn.execute(
            "INSERT INTO address (id_address, id_user, zipcode, street, number, city, state, "
            "neighborhood, created_at) "
            "VALUES ($1, $2, '06000000', 'Rua das Flores', $3, $4, 'SP', $5, $6)",
            f"{PREFIXO}end_{i}", id_user, str(10 + i), cidade, bairro,
            agora - timedelta(days=90),
        )

        for n in range(random.choice((1, 1, 2))):
            criada = agora - timedelta(days=random.randint(2, 88), hours=random.randint(0, 20))
            ativa = n == 0 and random.random() < 0.6
            id_donation = f"{PREFIXO}don_{i}_{n}"
            await conn.execute(
                "INSERT INTO donation (id_donation, created_by, is_active, is_recurrent, "
                "score_feedback, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
                id_donation, id_user, ativa, random.random() < 0.35,
                None if ativa else random.choice((4, 5, 5, 5, 3, None)), criada,
            )

            alcance = random.randint(1, 4) if ativa else 4
            momento = criada
            for ordem in range(alcance):
                ultima = ordem == alcance - 1
                momento = momento + timedelta(days=random.uniform(1.5, 9 if ordem == 2 else 5))
                if ativa and ultima:
                    status = random.choice(("pending", "pending", "review", "warn"))
                    concluida = None
                else:
                    status = "done"
                    concluida = min(momento, agora - timedelta(hours=2))

                id_step = f"{PREFIXO}st_{i}_{n}_{ordem}"
                await conn.execute(
                    "INSERT INTO donation_step (id_donation_step, id_donation, id_address, name, "
                    "status, set_date, created_at, completed_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    id_step, id_donation, f"{PREFIXO}end_{i}", ETAPAS[ordem], status,
                    momento, momento - timedelta(days=1), concluida,
                )
                if ordem in (1, 2):
                    etapas_por_regiao.setdefault((cidade, bairro), []).append(id_step)

                if ordem == 0 or status != "done" or random.random() < 0.3:
                    situacao = (
                        "pending" if status != "done"
                        else random.choice(("done", "done", "done", "failed"))
                    )
                    await conn.execute(
                        "INSERT INTO job (id_job, id_user, id_step, status, name, date_set, "
                        "created_at, created_by) "
                        "VALUES ($1, $2, $3, $4, 'Atendimento', $5, $6, 'seed')",
                        f"{PREFIXO}job_{i}_{n}_{ordem}", random.choice(enfermeiras), id_step,
                        situacao, momento, momento - timedelta(days=2),
                    )

            if alcance == 4 or (not ativa and alcance >= 3):
                for f in range(random.randint(6, 16)):
                    await conn.execute(
                        "INSERT INTO bottle (id_bottle, id_donation, quantity_donated_ml, "
                        "discarded, created_at) VALUES ($1, $2, $3, $4, $5)",
                        f"{PREFIXO}fr_{i}_{n}_{f}", id_donation,
                        random.choice((150, 180, 200, 220, 250)), random.random() < 0.08, momento,
                    )

    return etapas_por_regiao


async def _rotas(
    conn: asyncpg.Connection,
    motoristas: list[str],
    etapas_por_regiao: dict[tuple[str, str], list[str]],
) -> None:
    agora = _agora()
    regioes = list(etapas_por_regiao.items())

    for r in range(58):
        (cidade, bairro), etapas = regioes[r % len(regioes)]
        dia = agora - timedelta(days=88 - r * 1.5, hours=random.randint(0, 3))
        inicio = fim = km = None

        if r == 57:
            status, inicio = "in_progress", agora - timedelta(hours=5, minutes=12)
        elif r == 56:
            status, inicio = "in_progress", agora - timedelta(hours=1, minutes=40)
        elif r == 55:
            status, dia = "pending", agora + timedelta(hours=3)
        elif r % 17 == 0:
            status = "canceled"
        else:
            horas = random.choice((3.2, 3.8, 4.1, 4.5, 4.9, 5.3, 5.6, 6.4, 3.5, 4.0))
            status = "error" if r % 13 == 0 else "done"
            inicio = dia + timedelta(hours=8)
            fim = inicio + timedelta(hours=horas)
            km = round(random.uniform(22, 78), 1)

        id_route = f"{PREFIXO}rota_{r}"
        await conn.execute(
            "INSERT INTO route (id_route, id_driver, name, status, date_set, date_start, "
            "date_end, mileage, city, neighborhood, estimated_time, created_at, created_by) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'seed')",
            id_route, random.choice(motoristas), f"{bairro} - {dia:%d/%m}", status, dia,
            inicio, fim, km, cidade, bairro, int(random.uniform(3, 5) * 3.6e12),
            dia - timedelta(days=1),
        )

        quantidade = min(len(etapas), random.randint(2, 5))
        for p, id_step in enumerate(random.sample(etapas, quantidade)):
            if status in ("done", "error"):
                situacao = "error" if random.random() < 0.07 else "done"
            elif status == "in_progress":
                situacao = "done" if p < 2 else "pending"
            else:
                situacao = "pending"
            await conn.execute(
                "INSERT INTO route_donation_step (id_route_donation_step, id_route, "
                "id_donation_step, stop_order, status, created_at, created_by) "
                "VALUES ($1, $2, $3, $4, $5, $6, 'seed')",
                f"{PREFIXO}par_{r}_{p}", id_route, id_step, p + 1, situacao, dia,
            )


async def semear() -> None:
    _garantir_banco_local()
    random.seed(26)
    conn = await asyncpg.connect(_url_do_banco())
    try:
        await conn.execute(ESQUEMA.read_text(encoding="utf-8"))
        async with conn.transaction():
            await _limpar(conn)
            motoristas, enfermeiras = await _equipe(conn)
            etapas_por_regiao = await _doadoras(conn, enfermeiras)
            await _rotas(conn, motoristas, etapas_por_regiao)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(semear())
    print("Seed operacional aplicado no banco local.")
