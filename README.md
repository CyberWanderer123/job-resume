# AI Resume Parser and Job Matcher

An AI-powered job matching system that automatically scrapes job postings and matches them to your resume using OpenAI, Firecrawl, and Streamlit.

## Features

- Parse resumes from PDF URLs
- Scrape job listings from company career pages
- Analyze job fit using Claude 3.5 Sonnet
- Send Discord notifications for matching jobs
- Automated weekly job checks via GitHub Actions
- User-friendly Streamlit interface

## Tech Stack

- [Firecrawl](https://firecrawl.ai) for AI-powered web scraping
- [OpenAI GPT-4](https://openai.com) for job matching
- [Supabase](https://supabase.com) for data management
- [Discord](https://discord.com) for notifications
- [Streamlit](https://streamlit.io) for user interface
- [GitHub Actions](https://github.com/features/actions) for automation

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- API keys for Firecrawl, OpenAI, and Supabase
- Discord webhook URL for notifications
- A publicly accessible PDF URL for your resume

### Installation

1. Clone this repository:
```
git clone <repository-url>
cd job-resume
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with the following variables:
```
FIRECRAWL_API_KEY=your_firecrawl_api_key
OPENAI_API_KEY=your_openai_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook_url
RESUME_URL=your_resume_pdf_url
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### Supabase Setup

1. Create a new Supabase project
2. Create a table named `job_sources` with the following columns:
   - `url` (text, primary key)
   - `last_checked` (timestamp with time zone, nullable)

### Running the App

To run the Streamlit interface:
```
streamlit run app.py
```

To run the scheduler manually:
```
python -m src.scheduler
```

### GitHub Actions Setup

For automated weekly job checks:

1. Add all required secrets to your GitHub repository:
   - FIRECRAWL_API_KEY
   - OPENAI_API_KEY
   - DISCORD_WEBHOOK_URL
   - RESUME_URL
   - SUPABASE_URL
   - SUPABASE_KEY

2. Push to the main branch to enable the workflow

## Usage

1. Add job sources (company career pages) in the sidebar
2. Enter your resume PDF URL in the main section
3. Click "Analyze" to process jobs
4. View results and receive Discord notifications for matches

## Notes

- The app works best with company career pages rather than job aggregators
- Discord notifications are only sent for jobs that match your qualifications
- The weekly scheduler checks for new jobs every Monday at midnight
