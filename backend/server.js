// server.js
require('dotenv').config();
const express = require('express');
const app = express();

const { agentExecutor, testFastAPIConnection } = require('./agents/agent');
const pool = require('./db');
const {
  upsertGoal,
  upsertPhase,
  insertTask,
  linkMany,
} = require('./models/planModel');

app.use(express.json());

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:5000';

/* ---------- Health ---------- */
app.get('/health', async (_, res) => {
  const fastApiHealthy = await testFastAPIConnection();
  res.json({
    node: 'healthy',
    fastapi: fastApiHealthy ? 'healthy' : 'unhealthy',
    fastApiUrl: FASTAPI_URL,
  });
});

app.get('/', (_, res) =>
  res.json({ 
    message: 'Node.js server is running', 
    endpoints: ['/plan', '/plan/submit', '/plan/auto-save', '/health'] 
  })
);

/* ---------- Helper function to save plan to database ---------- */
async function savePlanToDatabase(goal, tasks) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // 1) Upsert the goal
    const goalId = await upsertGoal(goal);

    // 2) Walk through tasks, grouping by phase
    let currentPhase = null;
    let phaseOrder = 0;

    for (const item of tasks) {
      // detect new phase
      if (item.step !== currentPhase) {
        currentPhase = item.step;
        phaseOrder += 1;
      }
      // 3) Upsert phase
      const phaseId = await upsertPhase(goalId, item.step, phaseOrder);

      // 4) Insert task
      const taskId = await insertTask(
        goalId,
        phaseId,
        {
          task: item.task,
          description: item.description,
          estimated_time: item.estimated_time
        }
      );

      // 5) Link technologies
      await linkMany(taskId, item.technologies, 'technologies', 'task_technologies', 'technology_id');

      // 6) Link deliverables
      await linkMany(taskId, item.deliverables, 'deliverables', 'task_deliverables', 'deliverable_id');
    }

    await client.query('COMMIT');
    return goalId;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

/* ---------- Plan generator (LLM only) - Original endpoint ---------- */
app.post('/plan', async (req, res) => {
  const goal = (req.body.goal || '').trim();

  if (goal.length < 10) {
    return res
      .status(400)
      .json({ error: 'Goal must be a meaningful objective (≥ 10 chars)' });
  }

  // Ensure Python FastAPI service is reachable
  if (!(await testFastAPIConnection())) {
    return res.status(503).json({
      error: 'FastAPI service is unavailable. Start it and try again.',
      hint: 'python main.py',
    });
  }

  try {
    const tasks = await agentExecutor(goal);
    res.json({ goal, tasks });
  } catch (err) {
    console.error('Agent error:', err);
    res.status(500).json({ error: 'Agent failed to process your goal.', details: err.message });
  }
});

/* ---------- NEW: Auto-save plan (Generate + Save automatically) ---------- */
app.post('/plan/auto-save', async (req, res) => {
  const goal = (req.body.goal || '').trim();

  if (goal.length < 10) {
    return res
      .status(400)
      .json({ error: 'Goal must be a meaningful objective (≥ 10 chars)' });
  }

  // Ensure Python FastAPI service is reachable
  if (!(await testFastAPIConnection())) {
    return res.status(503).json({
      error: 'FastAPI service is unavailable. Start it and try again.',
      hint: 'python main.py',
    });
  }

  try {
    // Step 1: Generate tasks using AI
    console.log('🤖 Generating tasks for goal:', goal);
    const tasks = await agentExecutor(goal);
    console.log('✅ Tasks generated successfully');

    // Step 2: Automatically save to database
    console.log('💾 Saving plan to database...');
    const goalId = await savePlanToDatabase(goal, tasks);
    console.log('✅ Plan saved successfully with goalId:', goalId);

    // Step 3: Return both the tasks and confirmation
    res.json({ 
      goal, 
      tasks, 
      goalId,
      message: 'Plan generated and saved successfully!',
      status: 'success'
    });

  } catch (err) {
    console.error('❌ Auto-save error:', err);
    res.status(500).json({ 
      error: 'Failed to generate and save plan', 
      details: err.message 
    });
  }
});

/* ---------- Plan submit (persist to PostgreSQL) - Keep original for manual save ---------- */
app.post('/plan/submit', async (req, res) => {
  const { goal, tasks } = req.body;
  if (typeof goal !== 'string' || !Array.isArray(tasks) || tasks.length === 0) {
    return res.status(400).json({ error: 'Must provide { goal: string, tasks: [] } in body' });
  }

  try {
    const goalId = await savePlanToDatabase(goal, tasks);
    res.json({ message: 'Plan saved successfully', goalId });
  } catch (err) {
    console.error('DB save error:', err);
    res.status(500).json({ error: 'Failed to save plan', details: err.message });
  }
});

/* ---------- Test DB connection ---------- */
app.get('/test-db', async (req, res) => {
  try {
    await pool.query('SELECT 1');
    res.json({ message: 'Successfully connected to DB' });
  } catch (error) {
    console.error('DB connection error', error);
    res.status(500).json({ error: 'Database connection failed' });
  }
});

/* ---------- Boot ---------- */
const PORT = process.env.PORT || 8000;
app.listen(PORT, () =>
  console.log(`✅  Server running → http://localhost:${PORT}`)
);