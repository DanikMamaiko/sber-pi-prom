-- Разовая корректировка данных под правило декомпозиции.
--
-- Правило: история и подзадача не могут быть запланированы в спринт/неделю позже
-- своей инициативы («главной задачи»). Реализовано в backend/app/services/team_boards.py
-- (_validate_decomposition_period) и защищено на фронте (decompositionAfterIssue /
-- issueHasChildrenAfter) в коммите 886cb0d. Данные, созданные ДО этого коммита, могут
-- нарушать правило: тогда bulk-PUT /team-boards падает с 422 и блокирует сохранение
-- всей доски (варнинг «Не удалось сохранить командные доски…»).
--
-- Скрипт идемпотентный: повторный запуск не делает ничего. Дочерний элемент,
-- оказавшийся позже инициативы, подтягивается к спринту инициативы (week → NULL),
-- порядок (sort_order) не трогается. Запускать от имени прикладного пользователя БД
-- с правами UPDATE на stories/work_items; после — перезагрузить фронтенд, чтобы
-- контрольные суммы досок пересчитались с актуальными данными.
--
-- Применение (пример для контура с внешней PostgreSQL):
--   psql -v ON_ERROR_STOP=1 -d sberpi -f deploy/db/fix_decomposition_periods.sql

BEGIN;

-- Истории позже своей инициативы → подтянуть к спринту инициативы.
UPDATE stories AS s
SET sprint_index = i.sprint_index,
    week_index = NULL
FROM initiatives AS i
WHERE s.initiative_id = i.id
  AND i.sprint_index IS NOT NULL
  AND s.sprint_index IS NOT NULL
  AND (
        s.sprint_index > i.sprint_index
     OR (s.sprint_index = i.sprint_index
         AND s.week_index IS NOT NULL
         AND i.week_index IS NOT NULL
         AND s.week_index > i.week_index)
  );

-- Подзадачи (work_items) позже своей инициативы → подтянуть к спринту инициативы.
UPDATE work_items AS w
SET sprint_index = i.sprint_index,
    week_index = NULL
FROM initiatives AS i
WHERE w.initiative_id = i.id
  AND i.sprint_index IS NOT NULL
  AND w.sprint_index IS NOT NULL
  AND (
        w.sprint_index > i.sprint_index
     OR (w.sprint_index = i.sprint_index
         AND w.week_index IS NOT NULL
         AND i.week_index IS NOT NULL
         AND w.week_index > i.week_index)
  );

COMMIT;
