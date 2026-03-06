# AI personal Employee Vault - Silver Tier

Welcome to the AI Employee Vault, a complete file management and automation system built for the Personal AI Employee Hackathon 0. This system implements a robust workflow for processing files and tasks using AI-powered automation.

## 🏆 Silver Tier Achievements

This project successfully implements all Silver Tier requirements for the Personal AI Employee Hackathon, featuring automated file processing, task management, and AI-driven workflows.

## 📁 Folder Structure

- `/Inbox` - Incoming files awaiting processing
- `/Needs_Action` - Files requiring attention with metadata
- `/Done` - Completed tasks and processed files
- `/Plans` - Action plans and task breakdowns
- `/Logs` - System logs and processing history
- `/Pending_Approval` - Files requiring manual approval
- `/Skills` - AI skill definitions and instructions
- `/watchers` - File system monitoring scripts

## ⚙️ Core Components

### Dashboard.md
Central monitoring dashboard showing:
- Recent activity log
- Pending tasks counter
- Bank balance summary
- System status indicators
- Active agent skills

### Company_Handbook.md
Comprehensive rules of engagement including:
- Professional communication standards
- Financial protocols (payment thresholds, approval processes)
- Task management guidelines
- Quality assurance procedures

### File System Watcher
Automated file monitoring system that:
- Monitors the `/Inbox` folder for new files
- Copies original files to `/Needs_Action` with `FILE_` prefix
- Creates companion `.md` metadata files with YAML frontmatter
- Tracks file type, original name, size, timestamp, priority, and status

### Agent Skills

#### @Basic_File_Handler
- Reads .md files from `/Needs_Action`
- Summarizes content and creates action plans
- Generates `Plan.md` with simple checkboxes
- Moves completed files to `/Done` folder
- References `Company_Handbook.md` for compliance

#### @Task_Analyzer
- Analyzes all files in `/Needs_Action`
- Identifies file types (file drop, email, etc.)
- Creates action plans in `Plan.md`
- Checks for approval requirements (e.g., payments > $500)
- Routes to `/Pending_Approval` when needed
- Implements Ralph Wiggum persistence mindset for multi-step tasks

## 🛠️ Setup and Installation

1. Clone or download this repository
2. Install required dependencies:
   ```bash
   pip install watchdog
   ```
3. Start the file system watcher:
   ```bash
   python watchers/filesystem_watcher.py
   ```

## 🚀 Usage

1. Place files in the `/Inbox` folder
2. The system automatically detects new files
3. Files are copied to `/Needs_Action` with `FILE_` prefix
4. Companion metadata files are created with YAML frontmatter
5. Use agent skills (`@Basic_File_Handler`, `@Task_Analyzer`) to process tasks
6. Completed files are moved to `/Done` folder
7. Plans are created in `/Plans` folder

## 📊 File Format Specifications

### Metadata File Format (.md)
```yaml
---
type: file_drop
original_name: [original filename]
size: [size in bytes]
received: [ISO timestamp]
priority: medium
status: pending
---
## File Drop for Processing

New file dropped into Inbox. Ready for analysis.
```

### Agent Skill Format
Each skill follows the standard template with:
- Frontmatter (name, description, triggers, author, version)
- Detailed steps and process description
- Usage examples
- Compliance references

## 🧠 AI-Powered Features

- Automated file classification and routing
- Intelligent approval workflow
- Persistent task completion (Ralph Wiggum mindset)
- Compliance checking against company handbook
- Real-time dashboard updates

## 📈 Bronze Tier Validation

This system has been validated to meet all Bronze Tier requirements:
- ✅ Complete folder structure
- ✅ Core files with proper content
- ✅ Agent skills with correct functionality
- ✅ File system watcher with exact specifications
- ✅ File read/write capabilities proven
- ✅ End-to-end workflow simulation

## 🔄 Future Enhancements (Silver/Gold Tiers)

- Advanced AI processing capabilities
- Integration with external APIs
- Enhanced reporting and analytics
- Machine learning for task prioritization
- Natural language processing for content analysis

## 🤝 Contributing

This project is designed as part of the Personal AI Employee Hackathon. Contributions should follow the established patterns for file processing and agent skill definitions.

## 📄 License

Built for educational purposes as part of the Personal AI Employee Hackathon 0.
