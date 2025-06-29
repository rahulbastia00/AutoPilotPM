require("dotenv").config();
const express = require("express");
const { agentExecutor } = require("./agents/agent");

const app = express();
app.use(express.json());

// Health check endpoint
app.get("/", (req, res) => {
  res.json({ 
    message: "Node.js server is running", 
    endpoints: ["/plan"],
    status: "healthy"
  });
});

// POST /plan - { "goal": "Build a customer feedback system" }
app.post("/plan", async (req, res) => {
  const { goal } = req.body;
  
  if (!goal) {
    return res.status(400).json({ error: 'Request body must include "goal"' });
  }

  // Validate that goal is product management related
  if (typeof goal !== 'string' || goal.trim().length < 10) {
    return res.status(400).json({ 
      error: 'Goal must be a detailed product management objective (at least 10 characters)' 
    });
  }

  try {
    console.log(`Processing goal: ${goal}`);
    const tasks = await agentExecutor(goal);
    res.json({ tasks });
  } catch (err) {
    console.error("Agent error:", err);
    res.status(500).json({ 
      error: "Agent failed to process your goal. Please check if FastAPI service is running.",
      details: err.message 
    });
  }
});

const PORT = process.env.PORT;
app.listen(PORT, () =>
  console.log(`✅ Node.js server ready → http://localhost:${PORT}`)
);