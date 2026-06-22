# Extracted Project Specification

_Source: `Lead Discovery & Qualification Agent.docx`_

Lead Discovery & Qualification Agent

Objective

Build an AI-powered lead discovery and qualification system that identifies companies likely to benefit from Neodym's AI consulting, automation, and product development services.

The goal is not to build a generic lead scraper. The goal is to identify companies where AI could create measurable business value and provide actionable outreach intelligence.

We want to:

Build practical AI systems

Make engineering decisions independently

Use AI tools effectively

Deliver business value

Design useful workflows

Ship working software

Business Context

Neodym works with US based companies that can benefit from:

Workflow automation

AI-powered internal tools

AI agents

Customer support automation

Document processing

Knowledge retrieval systems

Operational efficiency improvements

Custom AI products

Examples (US based) may include:

Healthcare organizations

Legal firms

Small Businesses that don’t have websites

Logistics companies

Insurance businesses

Recruiting agencies

Professional services firms

SMB software companies

Growing technology companies

The system should help identify organizations where these opportunities may exist.

Project Overview

Build a system that:

Discovers potential companies

Evaluates fit for Neodym

Identifies likely pain points

Identifies potential AI opportunities

Produces a ranked lead list

The output should help answer:

Which companies should Neodym contact?

Why are they a good fit?

What problems could Neodym solve?

Who should we contact?

Core Requirements

Lead Discovery

Collect companies from one or more sources. Use the free tiers/plans initially

Possible sources:

Apollo exports

Company websites

Business directories

LinkedIn company information

Public databases

Job postings

Search results

The exact approach is up to you.

The system should demonstrate the ability to identify and evaluate at least 50 potential leads.

Company Analysis

For each company gather information such as:

Company name

Website

Industry

Location

Company description

Company size (if available)

Additional enrichment is encouraged.

Opportunity Detection

For each company identify potential AI opportunities.

Examples:

Customer Support

AI support agents

Knowledge assistants

Ticket automation

Operations

Workflow automation

Internal copilots

Process optimization

Document Workflows

Information extraction

Search systems

Summarization

Sales & Marketing

Lead qualification

CRM automation

Sales intelligence

The system should explain why each opportunity was identified.

Lead Scoring

Each company should receive:

Fit Score (1–10)

Score Reason

Likely Pain Point

Potential AI Opportunity

The scoring methodology should be explainable.

Example factors may include:

Industry relevance

Company size

Operational complexity

Hiring activity

Growth signals

Opportunity potential

Contact Identification

Where possible, identify relevant decision makers.

Examples:

Founder

CEO

CTO

Head of Operations

VP Engineering

Director of Technology

Include publicly available contact information when available.

AI Requirements

The project must use LLMs or AI-assisted reasoning for meaningful parts of the workflow.

Examples:

Opportunity identification

Lead scoring

Pain point detection

Company analysis

Simple data collection is not sufficient.

Use of Codex, Hermes, and other approved AI tooling is encouraged.

Because we do not currently have production LLM API access, design the system so that it can operate with available tooling and clearly document where future API integrations could be added.

Output Requirements

Structured Output

Generate:

lead_list.json

Each lead should include:

Company

Website

Industry

Contact

Fit Score

Reason

Pain Point

Opportunity

Source Links

Human-Readable Report

Generate:

lead_report.md

Present the highest-quality opportunities first.

Example:

Company: ABC Logistics

Fit Score: 9.2

Reason:
Growing logistics company with operational workflows that could benefit from automation.

Likely Pain Point:
Manual dispatch and customer communication processes.

Potential AI Opportunity:
Dispatch assistant, support automation, internal operations copilot.

Suggested Contact:
Head of Operations

Source:
Company website

Evaluation

Include a lightweight evaluation process that validates:

Output schema

Duplicate detection

Lead scoring consistency

Source grounding

Document how evaluations are run.

Deliverables

Source Code

GitHub repository

Working Product

Required:

Local run instructions

Optional:

Deployment URL

Weekly Lead Digest

Every week the system generates and sends an email to an internal Neodym address containing:

Top 10 leads

Company name

Fit score

Why they are a fit

Likely pain point

Suggested AI opportunity

Suggested contact

Generated Outputs

Include:

lead_list.json

lead_report.md

Documentation

README should include:

Setup instructions

Architecture overview

Data sources

Scoring methodology

AI usage

Limitations

Future improvements

Agent Usage Log

Include:

AI tools used

How they were used

What was manually verified

Problems encountered

Lessons learned

Evaluation Criteria

Engineering Execution

Code quality

Architecture

Reliability

Maintainability

Product Thinking

Lead quality

Relevance to Neodym

Business value

Opportunity identification

AI Integration

Workflow design

Prompt design

Reasoning quality

Data Quality

Source quality

Duplicate handling

Lead scoring consistency

Documentation & Communication

README quality

Demo quality

Clarity of explanation

Success Criteria

A successful submission should make a team member think:

"These are companies we should genuinely consider contacting, and I understand exactly why they are a good fit for Neodym."

Focus on lead quality and business value. Fifty mediocre leads are less valuable than ten highly qualified opportunities.
