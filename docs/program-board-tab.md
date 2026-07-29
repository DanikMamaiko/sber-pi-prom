# Вкладка Program Board

## Источник истины

Вкладка читает `GET /api/pi-cycles/{cycle_id}/program-board`. Read model строится backend только
из нормализованных сущностей выбранного PI: `PiCycleTeam`, `Initiative`, `InitiativeExecutor`,
`WorkItem`, `PiEvent` и `BoardConnection`. Копий инициатив или команд для Program Board нет.

Backend возвращает готовые спринты, строки трайбов/команд, карточки, связи и конфликты. В
`sessionStorage` сохраняются только настройки экрана; карточки, позиции, UUID и геометрия связей
там не хранятся. Отложенная полная замена Program Board из frontend удалена.

## Команды

- перенос карточки — `PATCH .../initiatives/{id}/position`;
- создание зависимости — `POST .../connections`;
- перенос endpoint или изменение изгиба — `PATCH .../connections/{id}`;
- удаление зависимости — `DELETE .../connections/{id}`.

Каждая команда содержит `expected_version`, выполняется под `SELECT ... FOR UPDATE`, увеличивает
`pi_cycles.version` в той же транзакции и возвращает полную каноническую проекцию. Устаревшая
команда получает 409 `version_conflict` и не повторяется автоматически.

## Общие сущности с командными досками

Program Board и «Командные доски» изменяют одну `Initiative.sprint_index`. После перемещения на
Program Board frontend перечитывает `/team-boards`; после команды командной доски перечитывается
Program Board. UUID инициатив, работ и зависимостей остаются стабильными после перезагрузки.

Удаление Work Item или Story с дочерними работами сначала возвращает 409
`cascade_confirmation_required`; после `confirm_cascade: true` endpoint и все его связи удаляются
одной транзакцией. Уникальность направленной связи дополнительно защищена ограничением PostgreSQL
`uq_board_connection_directed_edge`.

## Предупреждения

Read model сообщает об инициативе без спринта, позиции вне диапазона, отсутствии исполнителя
активного PI, зависимости с неназначенным endpoint и нарушении порядка спринтов. UI отображает
предупреждения над таблицей и помечает проблемные карточки.
