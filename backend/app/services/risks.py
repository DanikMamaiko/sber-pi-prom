import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import PiCycle, PiCycleTeam, Risk, Team, Tribe
from app.schemas.pi_cycle import RiskItemRead, RisksRead, RisksWrite


async def _cycle_team_map(
    session: AsyncSession,
    cycle_id: uuid.UUID,
) -> dict[tuple[str, str], Team]:
    rows = (
        await session.scalars(
            select(PiCycleTeam)
            .options(selectinload(PiCycleTeam.team).selectinload(Team.tribe))
            .where(PiCycleTeam.cycle_id == cycle_id)
        )
    ).all()
    return {
        (row.team.tribe.name.strip().casefold(), row.team.name.strip().casefold()): row.team
        for row in rows
    }


async def read_risks(
    session: AsyncSession,
    cycle: PiCycle,
) -> RisksRead:
    rows = (
        await session.scalars(
            select(Risk)
            .options(selectinload(Risk.team).selectinload(Team.tribe))
            .where(Risk.cycle_id == cycle.id)
            .order_by(Risk.scope, Risk.sort_order, Risk.created_at, Risk.id)
        )
    ).all()
    result: list[RiskItemRead] = []
    for risk in rows:
        team = None
        if risk.scope == "team" and risk.team is not None:
            team = {"tribe": risk.team.tribe.name, "name": risk.team.name}
        if risk.scope == "team" and team is None:
            continue
        result.append(
            RiskItemRead(
                id=risk.id,
                client_uid=risk.client_uid,
                scope=risk.scope,
                team=team,
                is_shared=risk.is_shared if risk.scope == "team" else False,
                description=risk.description,
                owner=risk.owner,
                impact=risk.impact,
                control_point=risk.control_point,
                mitigation_plan=risk.mitigation_plan,
                sort_order=risk.sort_order,
            )
        )
    return RisksRead(initialized=cycle.risks_initialized, version=cycle.version, risks=result)


async def replace_risks(
    session: AsyncSession,
    cycle: PiCycle,
    payload: RisksWrite,
) -> RisksRead:
    client_uids = [row.client_uid.strip().casefold() for row in payload.risks]
    if len(client_uids) != len(set(client_uids)):
        raise ValueError("Risk UID must be unique inside a PI cycle")

    teams = await _cycle_team_map(session, cycle.id)
    resolved: list[tuple] = []
    for source in payload.risks:
        team = None
        if source.scope == "general":
            if source.team is not None:
                raise ValueError("A general risk cannot reference a team")
            if source.is_shared:
                raise ValueError("Only a team risk can be shared")
        else:
            if source.team is None:
                raise ValueError("A team risk must reference a team")
            key = (source.team.tribe.strip().casefold(), source.team.name.strip().casefold())
            team = teams.get(key)
            if team is None:
                raise ValueError(
                    "Risk team is not found in this PI cycle: "
                    f"{source.team.tribe} / {source.team.name}"
                )
        resolved.append((source, team))

    existing = list(
        (
            await session.scalars(select(Risk).where(Risk.cycle_id == cycle.id))
        ).all()
    )
    existing_by_id = {row.id: row for row in existing}
    existing_by_uid = {row.client_uid.casefold(): row for row in existing}
    desired_ids: set[uuid.UUID] = set()

    for position, (source, team) in enumerate(resolved):
        uid = source.client_uid.strip()
        risk = existing_by_id.get(source.id) if source.id else None
        uid_match = existing_by_uid.get(uid.casefold())
        if source.id is not None and risk is None:
            raise ValueError(f"Risk ID is not found in this PI cycle: {source.id}")
        if risk is not None and uid_match is not None and risk.id != uid_match.id:
            raise ValueError(f"Risk ID does not match client UID: {uid}")
        if risk is None:
            risk = uid_match
        if risk is None:
            risk = Risk(
                id=uuid.uuid4(),
                cycle_id=cycle.id,
                client_uid=uid,
                description=source.description.strip(),
            )
            session.add(risk)
        risk.client_uid = uid
        risk.scope = source.scope
        risk.team_id = team.id if team else None
        risk.is_shared = source.is_shared if team else False
        risk.description = source.description.strip()
        risk.owner = source.owner.strip()
        risk.impact = source.impact.strip()
        risk.control_point = source.control_point.strip()
        risk.mitigation_plan = source.mitigation_plan.strip()
        risk.sort_order = source.sort_order if source.sort_order is not None else position
        desired_ids.add(risk.id)

    for risk in existing:
        if risk.id not in desired_ids:
            await session.delete(risk)
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)
