---
name: Basic File Handler
description: Reads .md files from /Needs_Action, summarizes content, creates Plan.md, and moves completed files to /Done
triggers: "@Basic_File_Handler or when a file needs basic processing"
author: AI Employee
version: 1.0
---

# Basic File Handler

## Description
This skill reads any .md file from /Needs_Action, summarizes its content, writes a clean Plan.md in /Plans/ with simple checkboxes for next steps, references Company_Handbook.md rules, moves completed files to /Done folder, and outputs a success message.

## Steps
1. Read all .md files in /Needs_Action folder
2. Summarize the content of each file
3. Reference Company_Handbook.md to ensure compliance with rules
4. Create a Plan.md in /Plans/ with simple checkboxes for next steps
5. Move completed files to /Done folder
6. Output success message with full file paths

## Detailed Process
- Scan /Needs_Action for .md files
- For each file, extract key information and requirements
- Generate a simple action plan with checkboxes in Plan.md
- Ensure all actions comply with Company_Handbook.md rules
- After completion, move the processed file to /Done folder
- Log success with full file paths

## Examples
Input: A file "Invoice_Request.md" in /Needs_Action
Process: Read the invoice request, create action plan in Plan.md, check handbook for payment rules
Output: Plan.md with invoice processing steps, Invoice_Request.md moved to /Done

## Usage
@Basic_File_Handler - Process any pending files in /Needs_Action with basic handling steps

## HandBook Compliance
Always reference Company_Handbook.md before taking any action to ensure compliance with company policies, especially financial protocols and communication standards.