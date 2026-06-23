<div align="center">

# 🚀 Nexa Agent

### Next-Generation AI Coding Agent for the Terminal

Build software, automate workflows, search the web, review code, interact with Google services, and control your development environment using natural language.

Powered by **OpenRouter** and modern **Large Language Models (LLMs).**

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)

![OpenRouter](https://img.shields.io/badge/OpenRouter-Multi_Model-purple?style=for-the-badge)

![Platform](https://img.shields.io/badge/Linux-Termux-black?style=for-the-badge)

![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

</p>

</div>

---

# 📖 What is Nexa Agent?

Nexa Agent is an open-source AI agent that transforms your terminal into an intelligent development environment.

Instead of acting like a traditional chatbot, Nexa Agent can interact with your local system using built-in tools to automate real development tasks.

Whether you're writing code, debugging applications, searching documentation, managing emails, or creating project files, Nexa Agent helps you complete tasks without constantly switching between applications.

Designed for developers, students, and power users, Nexa Agent combines AI reasoning with practical automation in one lightweight terminal application.

---

# ✨ Core Features

## 🤖 AI Coding Assistant

- Generate complete applications
- Explain source code
- Fix bugs
- Refactor projects
- Write documentation
- Optimize code
- Generate unit tests

---

## 📂 Smart File Management

- Read files
- Create files
- Edit files
- Replace text
- Delete files
- Rename files
- Search project files

---

## 💻 Interactive Terminal

Execute commands directly.

Examples:

- git clone
- git status
- python app.py
- pip install
- npm install
- cargo build
- pytest

---

## 🌍 Real-Time Web Search

- Documentation
- AI News
- API References
- Framework Updates
- General Search

---

## 📺 YouTube Search

Search YouTube directly.

Returns:

- Video Title
- Channel
- Views
- Duration
- Upload Date
- Video URL

---

## 📈 Live Financial Data

Retrieve live prices.

Supports:

- Bitcoin
- Ethereum
- Solana
- Gold
- Stocks
- Exchange Rates

---

## 📧 Gmail Integration

- Read Inbox
- Search Emails
- Send Emails
- Draft Replies

---

## ☁ Google Drive

- Google Docs
- Google Sheets
- Google Slides
- PDFs
- Text Files

---

## 📅 Google Calendar

- Read Events
- Create Events
- Meeting Reminders

---

## 🛒 Marketplace Search

Supports:

- Shopee
- Tokopedia

---

## 🔍 AI Code Review

Analyze code quality.

Checks:

- Syntax Errors
- Security
- Performance
- Best Practices

---

## 📊 Project Analyzer

Displays:

- Languages
- Dependencies
- Framework
- Entry Point
- Folder Structure

---

## 🔄 Multi-Model Support

Compatible with every OpenRouter model.

---

## 🛡 Safe Execution

Confirmation before dangerous actions.

---

## ⚡ Beautiful Terminal UI

Powered by Rich.

- Markdown
- Syntax Highlighting
- Progress Bars
- Tables
- Panels

---

# 🎬 Examples

## 📺 Search YouTube

**Prompt**

```text
Search YouTube: AI Coding Agent Tutorial
```

**Response**

```text
🔍 Searching YouTube...

1. Build an AI Coding Agent
👤 Fireship
👁 1.2M Views
⏱ 15:43

2. AI Coding Tutorial
👤 Tech With Tim
👁 462K Views
⏱ 28:51
```

---

## 📈 Live Crypto Prices

**Prompt**

```text
BTC Price
```

**Response**

```text
Bitcoin (BTC)

Price
$106,245.17

24H
+2.61%

Market Cap
$2.11T

Volume
$34.2B
```

---

## 💻 Interactive Terminal

**Prompt**

```text
Run git status
```

**Response**

```text
> git status

On branch main

nothing to commit, working tree clean
```

---

## 📂 File Generation

**Prompt**

```text
Create Flask Login Page
```

**Response**

```text
✔ app.py

✔ templates/login.html

✔ static/style.css

✔ requirements.txt

Done.
```

---

## ✏ Smart File Editing

**Prompt**

```text
Add Dark Mode to index.html
```

**Response**

```text
Reading file...

Applying changes...

✔ Updated Successfully
```

---

## 🔍 AI Code Review

**Prompt**

```text
Review app.py
```

**Response**

```text
✔ Syntax Check Passed

Suggestions

• Remove unused imports

• Add exception handling

• Improve naming

Overall Score

9.6 / 10
```

---

## 🌐 Web Search

**Prompt**

```text
Latest Python Release
```

**Response**

```text
Python 3.15 Released

Highlights

• Faster Interpreter

• Better Typing

• Performance Improvements
```

---

## 📧 Gmail

**Prompt**

```text
Show unread emails
```

**Response**

```text
Inbox

GitHub

Security Alert

Google

Verification Code

OpenRouter

Usage Report
```

---

## 📅 Google Calendar

**Prompt**

```text
Create meeting tomorrow at 09:00
```

**Response**

```text
✔ Event Created

Tomorrow

09:00 - 10:00
```

---

## ☁ Google Drive

**Prompt**

```text
Find Project Proposal
```

**Response**

```text
Project Proposal.pdf

Owner: You

Modified: 2 Days Ago
```

---

## 🛒 Marketplace Search

**Prompt**

```text
Search Mechanical Keyboard
```

**Response**

```text
Shopee

Royal Kludge RK61

Rp499.000

★★★★★

Tokopedia

Ajazz AK820

Rp569.000

★★★★★
```

---

# 🚀 Quick Start

```bash
git clone https://github.com/rm6872487-source/Nexa-agent

cd Nexa-agent

pip install -r requirements.txt

export OPENROUTER_API_KEY=YOUR_API_KEY

python agent.py
```

---

# 📦 Requirements

Required

- Python 3.10+
- OpenRouter API Key
- Internet Connection

Optional

- Google OAuth Credentials
- Tavily API Key
- SearchAPI Key

---

# 🏗 Architecture

```text
                User
                  │
                  ▼
            Nexa Agent
                  │
      ┌───────────┼────────────┐
      │           │            │
      ▼           ▼            ▼
 OpenRouter   Local Tools   Web APIs
      │           │            │
      │           ├── File System
      │           ├── Terminal
      │           ├── Code Review
      │           └── Project Analyzer
      │
      └──────────────┬──────────────────
                     │
     ┌───────────────┼─────────────────┐
     ▼               ▼                 ▼
 Web Search      YouTube          Google APIs
                                     │
                      ┌──────────────┼─────────────┐
                      ▼              ▼             ▼
                    Gmail        Drive       Calendar
```

---

# 🛣 Roadmap

- AI Coding Assistant
- Interactive Terminal
- File Management
- Web Search
- YouTube Search
- Gmail Integration
- Google Drive
- Google Calendar
- Live Crypto Prices
- AI Code Review
- Project Analyzer
- Git Integration
- Multi-Agent Workflow
- Plugin System

---

# 🤝 Contributing

Pull requests, feature suggestions, and bug reports are always welcome.

---

# 📄 License

Released under the MIT License.
<p align="center">
  <img src="assets/banner.png" width="100%">
</p>

<h1 align="center">Nexa Agent</h1>

<p align="center">
Next-Generation AI Coding Agent for the Terminal
</p>

<p align="center">
Build • Search • Code • Execute • Automate
</p>

<p align="center">
<img src="https://img.shields.io/github/stars/rm6872487-source/Nexa-agent?style=for-the-badge">
<img src="https://img.shields.io/github/license/rm6872487-source/Nexa-agent?style=for-the-badge">
<img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge">
<img src="https://img.shields.io/badge/OpenRouter-Supported-purple?style=for-the-badge">
</p>

---

<p align="center">
<img src="assets/demo.gif" width="100%">
</p>

> Nexa Agent is an open-source AI coding agent capable of understanding projects, editing files, executing terminal commands, browsing the web, reviewing code, and interacting with Google services directly from your terminal.
