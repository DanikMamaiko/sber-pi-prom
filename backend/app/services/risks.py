import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pi_cycle import Initiative, PiCycle, PiCycleTeam, Risk, Team, Tribe
from app.schemas.pi_cycle import (
    RiskCreateCommand,
    RiskDeleteCommand,
    RiskLinkCommand,
    RiskReorderCommand,
    RiskRoamCommand,
    RiskStatusCommand,
    RiskUpdateCommand,
    RiskItemRead,
    RisksRead,
    RisksWrite,
)


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
            .options(
                selectinload(Risk.tribe),
                selectinload(Risk.team).selectinload(Team.tribe),
                selectinload(Risk.initiative),
            )
            .where(Risk.cycle_id == cycle.id)
            .order_by(Risk.sort_order, Risk.created_at, Risk.id)
        )
    ).all()
    result: list[RiskItemRead] = []
    for risk in rows:
        team = None
        link = None
        if risk.scope == "team" and risk.team is not None:
            team = {"tribe": risk.team.tribe.name, "name": risk.team.name}
            link = {
                "scope": "team",
                "team_id": risk.team_id,
                "team": risk.team.name,
                "tribe_id": risk.team.tribe_id,
                "tribe": risk.team.tribe.name,
            }
        elif risk.scope == "tribe" and risk.tribe is not None:
            link = {"scope": "tribe", "tribe_id": risk.tribe_id, "tribe": risk.tribe.name}
        elif risk.scope == "initiative" and risk.initiative is not None:
            link = {
                "scope": "initiative",
                "initiative_id": risk.initiative_id,
                "issue_key": risk.initiative.issue_key,
                "title": risk.initiative.title,
            }
        elif risk.scope == "general":
            link = {"scope": "general"}
        result.append(
            RiskItemRead(
                id=risk.id,
                client_uid=risk.client_uid,
                scope=risk.scope,
                tribe_id=risk.tribe_id,
                team_id=risk.team_id,
                initiative_id=risk.initiative_id,
                team=team,
                is_shared=risk.is_shared if risk.scope == "team" else False,
                description=risk.description,
                owner=risk.owner,
                impact=risk.impact,
                control_point=risk.control_point,
                mitigation_plan=risk.mitigation_plan,
                probability=risk.probability,
                impact_level=risk.impact_level,
                criticality=risk.criticality,
                criticality_label=_criticality_label(risk.criticality),
                reaction_due_date=risk.reaction_due_date,
                treatment_plan=risk.treatment_plan,
                status=risk.status,
                roam=risk.roam,
                link=link,
                sort_order=risk.sort_order,
            )
        )
    return RisksRead(
        initialized=cycle.risks_initialized,
        version=cycle.version,
        risks=result,
        reference_data=await _risks_reference_data(session, cycle),
    )


def _criticality(probability: int, impact_level: int) -> int:
    return max(1, min(5, int(probability))) * max(1, min(5, int(impact_level)))


def _criticality_label(value: int) -> str:
    if value >= 16:
        return "critical"
    if value >= 9:
        return "high"
    if value >= 4:
        return "medium"
    return "low"


async def _risks_reference_data(session: AsyncSession, cycle: PiCycle) -> dict:
    cycle_teams = (
        await session.scalars(
            select(PiCycleTeam)
            .options(selectinload(PiCycleTeam.team).selectinload(Team.tribe))
            .where(PiCycleTeam.cycle_id == cycle.id)
            .order_by(PiCycleTeam.sort_order, PiCycleTeam.id)
        )
    ).all()
    initiatives = (
        await session.scalars(
            select(Initiative)
            .where(Initiative.cycle_id == cycle.id)
            .order_by(Initiative.sort_order, Initiative.created_at, Initiative.id)
        )
    ).all()
    tribes_by_id: dict[uuid.UUID, Tribe] = {}
    teams = []
    for row in cycle_teams:
        if row.team and row.team.tribe:
            tribes_by_id[row.team.tribe.id] = row.team.tribe
            teams.append(
                {
                    "id": row.team.id,
                    "tribe_id": row.team.tribe.id,
                    "tribe": row.team.tribe.name,
                    "name": row.team.name,
                    "sort_order": row.sort_order,
                }
            )
    return {
        "tribes": [
            {"id": tribe.id, "name": tribe.name}
            for tribe in sorted(tribes_by_id.values(), key=lambda item: item.name)
        ],
        "teams": teams,
        "initiatives": [
            {"id": item.id, "issue_key": item.issue_key, "title": item.title}
            for item in initiatives
        ],
        "statuses": ["open", "watching", "closed"],
        "roam": ["resolved", "owned", "accepted", "mitigated"],
    }


async def _validate_tribe(
    session: AsyncSession,
    cycle: PiCycle,
    tribe_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if tribe_id is None:
        return None
    exists = await session.scalar(
        select(PiCycleTeam)
        .join(Team, PiCycleTeam.team_id == Team.id)
        .where(PiCycleTeam.cycle_id == cycle.id, Team.tribe_id == tribe_id)
    )
    if exists is None:
        raise ValueError("Трайб риска не входит в данный PI-цикл")
    return tribe_id


async def _validate_team(
    session: AsyncSession,
    cycle: PiCycle,
    team_id: uuid.UUID | None,
) -> Team | None:
    if team_id is None:
        return None
    cycle_team = await session.scalar(
        select(PiCycleTeam)
        .options(selectinload(PiCycleTeam.team))
        .where(PiCycleTeam.cycle_id == cycle.id, PiCycleTeam.team_id == team_id)
    )
    if cycle_team is None:
        raise ValueError("Команда риска не входит в данный PI-цикл")
    return cycle_team.team


async def _validate_initiative(
    session: AsyncSession,
    cycle: PiCycle,
    initiative_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if initiative_id is None:
        return None
    exists = await session.scalar(
        select(Initiative).where(Initiative.cycle_id == cycle.id, Initiative.id == initiative_id)
    )
    if exists is None:
        raise ValueError("Инициатива риска не входит в данный PI-цикл")
    return initiative_id


async def _apply_risk_link(
    session: AsyncSession,
    cycle: PiCycle,
    risk: Risk,
    *,
    scope: str,
    tribe_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
    initiative_id: uuid.UUID | None,
    is_shared: bool | None = None,
) -> None:
    if scope == "general":
        if tribe_id or team_id or initiative_id:
            raise ValueError("Общий риск не может ссылаться на трайб, команду или инициативу")
        risk.scope = "general"
        risk.tribe_id = None
        risk.team_id = None
        risk.initiative_id = None
        risk.is_shared = False
    elif scope == "tribe":
        risk.scope = "tribe"
        risk.tribe_id = await _validate_tribe(session, cycle, tribe_id)
        if risk.tribe_id is None:
            raise ValueError("Риск трайба должен ссылаться на трайб")
        risk.team_id = None
        risk.initiative_id = None
        risk.is_shared = False
    elif scope == "team":
        team = await _validate_team(session, cycle, team_id)
        if team is None:
            raise ValueError("Командный риск должен ссылаться на команду")
        risk.scope = "team"
        risk.tribe_id = team.tribe_id
        risk.team_id = team.id
        risk.initiative_id = None
        risk.is_shared = bool(is_shared)
    elif scope == "initiative":
        risk.scope = "initiative"
        risk.tribe_id = None
        risk.team_id = None
        risk.initiative_id = await _validate_initiative(session, cycle, initiative_id)
        if risk.initiative_id is None:
            raise ValueError("Риск инициативы должен ссылаться на инициативу")
        risk.is_shared = False
    else:
        raise ValueError("Неизвестная область риска")


async def _get_risk(session: AsyncSession, cycle: PiCycle, risk_id: uuid.UUID) -> Risk:
    risk = await session.scalar(
        select(Risk).where(Risk.cycle_id == cycle.id, Risk.id == risk_id)
    )
    if risk is None:
        raise ValueError("Риск не найден в данном PI-цикле")
    return risk


def _copy_risk_fields(risk: Risk, data: dict) -> None:
    for field in (
        "description",
        "owner",
        "impact",
        "control_point",
        "mitigation_plan",
        "probability",
        "impact_level",
        "reaction_due_date",
        "treatment_plan",
        "status",
        "roam",
    ):
        if field in data and data[field] is not None:
            value = data[field]
            setattr(risk, field, value.strip() if isinstance(value, str) else value)
    risk.criticality = _criticality(risk.probability, risk.impact_level)


async def create_risk_command(
    session: AsyncSession,
    cycle: PiCycle,
    payload: RiskCreateCommand,
) -> RisksRead:
    risk_id = uuid.uuid4()
    max_sort_order = await session.scalar(
        select(Risk.sort_order)
        .where(Risk.cycle_id == cycle.id)
        .order_by(Risk.sort_order.desc())
        .limit(1)
    )
    risk = Risk(
        id=risk_id,
        cycle_id=cycle.id,
        client_uid=f"risk-{risk_id}",
        description=payload.description.strip(),
        sort_order=(max_sort_order + 1 if max_sort_order is not None else 0),
    )
    session.add(risk)
    await _apply_risk_link(
        session,
        cycle,
        risk,
        scope=payload.scope,
        tribe_id=payload.tribe_id,
        team_id=payload.team_id,
        initiative_id=payload.initiative_id,
        is_shared=payload.is_shared,
    )
    _copy_risk_fields(risk, payload.model_dump())
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def update_risk_command(
    session: AsyncSession,
    cycle: PiCycle,
    risk_id: uuid.UUID,
    payload: RiskUpdateCommand,
) -> RisksRead:
    risk = await _get_risk(session, cycle, risk_id)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if any(key in data for key in ("scope", "tribe_id", "team_id", "initiative_id", "is_shared")):
        await _apply_risk_link(
            session,
            cycle,
            risk,
            scope=data.get("scope", risk.scope),
            tribe_id=data.get("tribe_id", risk.tribe_id),
            team_id=data.get("team_id", risk.team_id),
            initiative_id=data.get("initiative_id", risk.initiative_id),
            is_shared=data.get("is_shared", risk.is_shared),
        )
    _copy_risk_fields(risk, data)
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def delete_risk_command(
    session: AsyncSession,
    cycle: PiCycle,
    risk_id: uuid.UUID,
    payload: RiskDeleteCommand,
) -> RisksRead:
    _ = payload
    risk = await _get_risk(session, cycle, risk_id)
    await session.delete(risk)
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def reorder_risks_command(
    session: AsyncSession,
    cycle: PiCycle,
    payload: RiskReorderCommand,
) -> RisksRead:
    risks = (await session.scalars(select(Risk).where(Risk.cycle_id == cycle.id))).all()
    by_id = {risk.id: risk for risk in risks}
    if set(payload.risk_ids) != set(by_id):
        raise ValueError("Порядок должен включать все риски данного PI-цикла")
    for index, risk_id in enumerate(payload.risk_ids):
        by_id[risk_id].sort_order = index
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def update_risk_status_command(
    session: AsyncSession,
    cycle: PiCycle,
    risk_id: uuid.UUID,
    payload: RiskStatusCommand,
) -> RisksRead:
    risk = await _get_risk(session, cycle, risk_id)
    risk.status = payload.status
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def update_risk_roam_command(
    session: AsyncSession,
    cycle: PiCycle,
    risk_id: uuid.UUID,
    payload: RiskRoamCommand,
) -> RisksRead:
    risk = await _get_risk(session, cycle, risk_id)
    risk.roam = payload.roam
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def update_risk_link_command(
    session: AsyncSession,
    cycle: PiCycle,
    risk_id: uuid.UUID,
    payload: RiskLinkCommand,
) -> RisksRead:
    risk = await _get_risk(session, cycle, risk_id)
    await _apply_risk_link(
        session,
        cycle,
        risk,
        scope=payload.scope,
        tribe_id=payload.tribe_id,
        team_id=payload.team_id,
        initiative_id=payload.initiative_id,
        is_shared=risk.is_shared,
    )
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)


async def replace_risks(
    session: AsyncSession,
    cycle: PiCycle,
    payload: RisksWrite,
) -> RisksRead:
    client_uids = [row.client_uid.strip().casefold() for row in payload.risks]
    if len(client_uids) != len(set(client_uids)):
        raise ValueError("UID риска должен быть уникален в пределах PI-цикла")

    teams = await _cycle_team_map(session, cycle.id)
    resolved: list[tuple] = []
    for source in payload.risks:
        team = None
        if source.scope == "general":
            if source.team is not None:
                raise ValueError("Общий риск не может ссылаться на команду")
            if source.is_shared:
                raise ValueError("Общим может быть только командный риск")
        elif source.scope == "team":
            if source.team is None:
                raise ValueError("Командный риск должен ссылаться на команду")
            key = (source.team.tribe.strip().casefold(), source.team.name.strip().casefold())
            team = teams.get(key)
            if team is None:
                raise ValueError(
                    "Команда риска не найдена в данном PI-цикле: "
                    f"{source.team.tribe} / {source.team.name}"
                )
        elif source.scope == "tribe":
            await _validate_tribe(session, cycle, source.tribe_id)
        elif source.scope == "initiative":
            await _validate_initiative(session, cycle, source.initiative_id)
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
            raise ValueError(f"Риск не найден в данном PI-цикле: {source.id}")
        if risk is not None and uid_match is not None and risk.id != uid_match.id:
            raise ValueError(f"ID риска не соответствует клиентскому UID: {uid}")
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
        await _apply_risk_link(
            session,
            cycle,
            risk,
            scope=source.scope,
            tribe_id=source.tribe_id,
            team_id=team.id if team else source.team_id,
            initiative_id=source.initiative_id,
            is_shared=source.is_shared if team else False,
        )
        risk.description = source.description.strip()
        risk.owner = source.owner.strip()
        risk.impact = source.impact.strip()
        risk.control_point = source.control_point.strip()
        risk.mitigation_plan = source.mitigation_plan.strip()
        risk.probability = source.probability
        risk.impact_level = source.impact_level
        risk.criticality = _criticality(source.probability, source.impact_level)
        risk.reaction_due_date = source.reaction_due_date
        risk.treatment_plan = source.treatment_plan.strip()
        risk.status = source.status
        risk.roam = source.roam
        risk.sort_order = source.sort_order if source.sort_order is not None else position
        desired_ids.add(risk.id)

    for risk in existing:
        if risk.id not in desired_ids:
            await session.delete(risk)
    cycle.risks_initialized = True
    await session.commit()
    return await read_risks(session, cycle)
