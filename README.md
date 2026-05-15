# Sandboxed Algorithmic Judge & AI Code Reviewer

An enterprise-grade, highly secure, distributed code execution platform. This system securely compiles and runs untrusted user-submitted code (C++ and Python) in isolated Docker containers, measures execution time and memory limits, and uses a local Large Language Model (LLM) to provide architectural feedback and time/space complexity analysis.

## 🌟 What Does This Project Do?
Imagine you are building a coding platform like LeetCode or HackerRank. You need a way to run the code users submit safely, without letting their code hack your servers or consume all your system's memory. You also want to provide them with intelligent feedback on their code quality.

This project does exactly that. 
1. **Accepts Code:** You send it code via an API.
2. **Queues it:** It puts the code in a background queue so the API doesn't freeze under heavy load.
3. **Runs securely:** A background worker picks it up, creates a completely isolated, temporary "sandbox" environment (a Docker container without internet or system access), and runs the code inside it.
4. **Evaluates & Reviews:** It checks if the code succeeded or timed out. Then, it asks a local AI model (Qwen 2.5 Coder) to review the code and suggest improvements.
5. **Saves Results:** Finally, it saves the execution results and AI review in a database.

## 🏗️ Architecture & How It Works

* **FastAPI (Gateway):** The entry point. It receives the code and immediately returns a Tracking ID (Job ID).
* **PostgreSQL:** Stores the submission details, status, and final results securely.
* **Redis:** Acts as a message broker to queue the tasks for the workers.
* **Celery Worker:** Listens to the Redis queue, picks up code submissions, and coordinates the execution.
* **Docker Socket Proxy:** A security layer. The worker uses this proxy to launch isolated child Docker containers to run the untrusted code, preventing direct access to the main Docker daemon.
* **Ollama (AI Reviewer):** Runs a local LLM (`qwen2.5-coder`) to perform static analysis and review the submitted code without needing external paid APIs like OpenAI.

## 🚀 Features
- **True Isolation (DinD-Free Sandbox):** Uses sibling containers via a proxy. Code executes with zero network access, read-only filesystems, and strict memory limits.
- **Asynchronous Processing:** Handles thousands of submissions smoothly using Celery and Redis.
- **Multi-language Support:** Currently configured for Python 3 and C++ (with two-phase compile and execute).
- **AI-Powered Code Review:** Built-in integration with local LLMs to provide actionable feedback on time/space complexity and code design.
- **Hardened Security:** Execution containers run as the `nobody` user with all Linux privileges dropped (`cap_drop=["ALL"]`).

---

## 📁 Project Structure

```text
├── .env.example             # Example environment variables
├── Dockerfile               # Multi-stage Dockerfile for API and Celery Worker
├── docker-compose.yml       # Orchestrates all 6 services
├── requirements.txt         # Python dependencies
├── config.py                # Pydantic configuration and environment variables
├── database.py              # PostgreSQL database connection and session management
├── models.py                # SQLAlchemy ORM database tables (Submission model)
├── main.py                  # FastAPI Application (API Endpoints)
├── worker.py                # Celery background tasks and job orchestration
├── sandbox.py               # Docker SDK logic to safely execute untrusted code
├── ai_reviewer.py           # Logic to communicate with Ollama for AI reviews
└── ollama-entrypoint.sh     # Startup script to ensure the AI model is downloaded
```

---

## 🛠️ Installation & Setup

### Prerequisites
- **Docker** and **Docker Compose** installed on your system.
- (Optional) A system with an NVIDIA GPU for faster AI model inference.

### Step-by-Step Guide

1. **Clone the repository** (or navigate to the project folder).
2. **Setup Environment Variables:**
   ```bash
   # On Linux/macOS
   cp .env.example .env
   
   # On Windows (PowerShell)
   Copy-Item .env.example .env
   ```
3. **Start the System:**
   Run the following command to build and start all 6 services (Database, Redis, Proxy, Ollama, API, Worker).
   ```bash
   docker compose up --build -d
   ```
   > **Note:** The first time you run this, it will take several minutes to download the Docker images and pull the ~1.5GB `qwen2.5-coder` AI model inside the Ollama container.

4. **Verify it's running:**
   Ensure the API is healthy by visiting:
   [http://localhost:8000/health](http://localhost:8000/health)

---

## 💻 Usage & API Endpoints

Once the application is running, you can submit code using tools like `curl`, Postman, or any HTTP client.

### 1. Submit Code for Execution
**Endpoint:** `POST /submit`

**Example Request (Python):**
```bash
curl -X POST http://localhost:8000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "language": "python",
    "code": "def solve():\n    print(\"Hello from Sandbox!\")\n\nsolve()",
    "problem_id": "hello-world"
  }'
```

**Example Request (C++):**
```bash
curl -X POST http://localhost:8000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "language": "cpp",
    "code": "#include <iostream>\nint main() {\n    std::cout << \"Hello C++ Sandbox!\" << std::endl;\n    return 0;\n}",
    "problem_id": "hello-world-cpp"
  }'
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "QUEUED"
}
```

### 2. Check Execution Status and Results
**Endpoint:** `GET /status/{job_id}`

Use the `job_id` returned from the submit endpoint to poll the results.

**Example Request:**
```bash
curl http://localhost:8000/status/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Response (When Processing):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "RUNNING",
  "result": null
}
```

**Response (When Finished):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "SUCCESS",
  "result": {
    "output": "Hello from Sandbox!\n",
    "error": "",
    "execution_time_ms": 15,
    "ai_review": "### Code Review...\nThis code is functionally correct and has O(1) time complexity..."
  }
}
```

---

## 🛑 Stopping the System
To shut down the services and preserve your database data, run:
```bash
docker compose down
```
If you want to completely wipe the database and start fresh, run:
```bash
docker compose down -v
```
