const pool = require('../db')

async function upsertGoal(goalTxt){
    const {rows} = await pool.query(
        `INSERT INTO goals(goal_text)
        VALUES($1)
        RETURNING id`,
        [goalTxt]
    );
    return rows[0].id;
}

async function upsertPhase(goalId, phaseName, order){
    const {rows} = await pool.query(
        `INSERT INTO phases(goal_id, phase_name, step_order)
        VALUES($1, $2, $3)
        ON CONFLICT (goal_id, step_order) DO UPDATE SET phase_name = EXCLUDED.phase_name
        RETURNING id`,
        [goalId, phaseName, order]
    );
    return rows[0].id;
}

async function insertTask(goalId, phaseId, { task, description, estimated_time }) {
  const weeks = parseInt(estimated_time, 10) || null;
  const { rows } = await pool.query(
    `INSERT INTO tasks(goal_id, phase_id, task_name, description, estimated_weeks)
     VALUES($1,$2,$3,$4,$5)
     RETURNING id`,
    [goalId, phaseId, task, description, weeks]
  );
  return rows[0].id;
}

async function upsertLookup(table, name) {
  const { rows } = await pool.query(
    `INSERT INTO ${table}(name)
     VALUES ($1)
     ON CONFLICT (name) DO NOTHING
     RETURNING id`,
    [name]
  );
  if (rows.length) return rows[0].id;

  // if it already existed, fetch its id
  const { rows: existing } = await pool.query(
    `SELECT id FROM ${table} WHERE name = $1`,
    [name]
  );
  return existing[0].id;
}

async function linkMany(taskId, items, lookupTable, junctionTable, junctionCol) {
  if (!items || items.length === 0) return; // Handle empty arrays
  
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    for (let name of items) {
      const lookupId = await upsertLookup(lookupTable, name);
      await client.query(
        `INSERT INTO ${junctionTable}(task_id, ${junctionCol})
         VALUES($1,$2)
         ON CONFLICT DO NOTHING`,
        [taskId, lookupId]
      );
    }
    await client.query('COMMIT');
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}

module.exports = {
  upsertGoal,
  upsertPhase,
  insertTask,
  linkMany,
};