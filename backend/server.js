require("dotenv").config();
const express = require("express");
const { agentExecutor, testFastAPIConnection } = require("./agents/agent");

const app = express();
app.use(express.json());

// Health check endpoint
app.get("/", (req, res) => {
  res.json({
    message: "Node.js server is running",
    endpoints: ["/plan", "/health"],
    status: "healthy",
  });
});

// Health check with FastAPI connectivity test
app.get("/health", async (req, res) => {
  try {
    const fastApiHealthy = await testFastAPIConnection();
    res.json({
      nodeStatus: "healthy",
      fastApiStatus: fastApiHealthy ? "healthy" : "unhealthy",
      fastApiUrl: process.env.FASTAPI_URL || "http://localhost:5000",
    });
  } catch (error) {
    res.status(500).json({
      nodeStatus: "healthy",
      fastApiStatus: "error",
      error: error.message,
    });
  }
});

// POST /plan - { "goal": "Build a customer feedback system" }
app.post("/plan", async (req, res) => {
  const { goal } = req.body;

  console.log(`Received request with goal: ${goal}`);

  if (!goal) {
    return res.status(400).json({ error: 'Request body must include "goal"' });
  }

  // Validate that goal is product management related
  if (typeof goal !== "string" || goal.trim().length < 10) {
    return res.status(400).json({
      error:
        "Goal must be a detailed product management objective (at least 10 characters)",
    });
  }

  try {
    console.log(`Processing goal: ${goal}`);

    // Test FastAPI connection first
    const isConnected = await testFastAPIConnection();
    if (!isConnected) {
      return res.status(503).json({
        error:
          "FastAPI service is not available. Please ensure the Python server is running on port 5000.",
        suggestion: "Run: python main.py (or your FastAPI script)",
      });
    }

    const tasks = await agentExecutor(goal);

    console.log(`Successfully processed goal, returning ${tasks.length} tasks`);
    res.json({ tasks });
  } catch (err) {
    console.error("Agent error:", err);
    res.status(500).json({
      error: "Agent failed to process your goal.",
      details: err.message,
      timestamp: new Date().toISOString(),
    });
  }
});

const PORT = process.env.PORT || 8000;
app.listen(PORT, () => {
  console.log(`✅ Node.js server ready → http://localhost:${PORT}`);
  console.log(
    `FastAPI URL: ${process.env.FASTAPI_URL || "http://localhost:5000"}`
  );

  // Test FastAPI connection on startup
  setTimeout(async () => {
    const isConnected = await testFastAPIConnection();
    if (isConnected) {
      console.log("✅ FastAPI connection verified");
    } else {
      console.log(
        "❌ FastAPI connection failed - make sure Python server is running"
      );
    }
  }, 1000);
});
