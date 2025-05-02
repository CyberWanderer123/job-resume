import streamlit as st
import asyncio
import os
from dotenv import load_dotenv
from src.scraper import JobScraper
from src.matcher import JobMatcher
from src.discord import DiscordNotifier
from src.database import Database

load_dotenv()

async def process_job(scraper, matcher, notifier, job, resume_content):
    """Process a single job posting"""
    job_content = await scraper.scrape_job_content(job.url)
    result = await matcher.evaluate_match(resume_content, job_content)

    if result["is_match"]:
        await notifier.send_match(job, result["reason"])

    return job, result

async def main():
    st.title("Resume Parser and Job Matcher")

    # Initialize services
    scraper = JobScraper()
    matcher = JobMatcher()
    notifier = DiscordNotifier()
    db = Database()

    # Sidebar for managing job sources
    with st.sidebar:
        st.header("Manage Job Sources")
        new_source = st.text_input("Add Job Source URL")

        if st.button("Add Source"):
            db.save_job_source(new_source)
            st.success("Job source added!")

        # List and delete existing sources
        st.subheader("Current Sources")
        for source in db.get_job_sources():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.text(source.url)
            with col2:
                if st.button("Delete", key=source.url):
                    db.delete_job_source(source.url)
                    st.rerun()

    st.markdown(
        """
    This app helps you find matching jobs by:
    - Analyzing your resume from a PDF URL
    - Scraping job postings from your saved job sources
    - Using AI to evaluate if you're a good fit for each position

    Simply paste your resume URL below to get started!
    """
    )

    # Get default resume URL from .env file
    default_resume_url = os.getenv("RESUME_URL", "")
    
    resume_url = st.text_input(
        "**Enter Resume PDF URL**",
        value=default_resume_url,  # Use the URL from .env as default
        placeholder="https://www.website.com/resume.pdf",
    )

    if st.button("Analyze") and resume_url:
        st.info(f"Using resume URL: {resume_url}")
        
        with st.spinner("Parsing resume..."):
            try:
                resume_content = await scraper.parse_resume(resume_url)
                
                # Check if resume parsing was successful
                if resume_content.startswith("Error") or resume_content.startswith("Failed"):
                    st.error(f"Failed to parse resume: {resume_content}")
                    return
                    
                st.success(f"Successfully parsed resume ({len(resume_content)} characters)")
            except Exception as e:
                st.error(f"Error parsing resume: {str(e)}")
                return

        sources = db.get_job_sources()
        if not sources:
            st.warning("No job sources configured. Add some in the sidebar!")
            return

        with st.spinner("Scraping job postings..."):
            jobs = await scraper.scrape_job_postings([s.url for s in sources])

        with st.spinner(f"Analyzing {len(jobs)} jobs..."):
            tasks = []
            for job in jobs:
                task = process_job(scraper, matcher, notifier, job, resume_content)
                tasks.append(task)

            for coro in asyncio.as_completed(tasks):
                job, result = await coro
                st.subheader(f"Job: {job.title}")
                st.write(f"URL: {job.url}")
                st.write(f"Match: {'✅' if result['is_match'] else '❌'}")
                st.write(f"Reason: {result['reason']}")
                st.divider()

        st.success(f"Analysis complete! Processed {len(jobs)} jobs.")

if __name__ == "__main__":
    asyncio.run(main())
