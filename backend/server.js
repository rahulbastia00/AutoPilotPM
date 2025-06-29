
require("dotenv").config();
const express = require("express");
const { agentExecutor } = require("./agents/agent");   // ⬅ pulls in the LLM agent

const app = express();
app.use(express.json());

// POST /plan  { "goal": "Build a customer feedback system" }
app.post("/plan", async (req, res) => {
  const { goal } = req.body;
  if (!goal) {
    return res.status(400).json({ error: 'Request body must include "goal"' });
  }

  try {
    const tasks = await agentExecutor(goal);   // ask the LLM to break it down
    res.json({ tasks });                       // same shape as your FastAPI reply
  } catch (err) {
    console.error("Agent error:", err);
    res.status(500).json({ error: "Agent failed – check server logs" });
  }
});

const PORT = process.env.PORT || 8000;
app.listen(PORT, () =>
  console.log(`✅ Server ready → POST http://localhost:${PORT}`)
);
