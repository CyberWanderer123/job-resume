from typing import List
import streamlit as st
import os
import requests
import io
import tempfile
from firecrawl import FirecrawlApp
from .models import Job

# Import PyPDF2 for direct PDF parsing
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("PyPDF2 not available. Install with 'pip install PyPDF2' for better PDF parsing.")

# Function to download a file from a URL
def download_file(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.content
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return None

@st.cache_data(show_spinner=False)
def _cached_parse_resume(pdf_link: str) -> str:
    """Cached version of resume parsing with direct PDF extraction"""
    try:
        print(f"Parsing resume from: {pdf_link}")
        
        # Special handling for Google Drive links
        if "drive.google.com" in pdf_link:
            print("Detected Google Drive link, converting to direct download URL...")
            # Extract the file ID from the URL
            file_id = None
            
            # Handle different Google Drive URL formats
            if "/file/d/" in pdf_link:
                # Format: https://drive.google.com/file/d/FILE_ID/view
                file_id = pdf_link.split("/file/d/")[1].split("/")[0]
            elif "id=" in pdf_link:
                # Format: https://drive.google.com/open?id=FILE_ID
                file_id = pdf_link.split("id=")[1].split("&")[0]
            
            if file_id:
                # Create direct download URL
                pdf_link = f"https://drive.google.com/uc?export=download&id={file_id}"
                print(f"Using direct download URL: {pdf_link}")
            else:
                print("Could not extract file ID, using original URL")
                # If we can't extract the ID, at least try to use preview instead of view
                if "/view" in pdf_link:
                    pdf_link = pdf_link.replace("/view", "/preview")
                    print(f"Using preview URL instead: {pdf_link}")
        
        # Try direct PDF extraction first if PyPDF2 is available
        content = ""
        if PYPDF2_AVAILABLE:
            print("Attempting direct PDF extraction with PyPDF2...")
            try:
                # Download the PDF file
                pdf_data = download_file(pdf_link)
                if pdf_data:
                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                        temp_file.write(pdf_data)
                        temp_path = temp_file.name
                    
                    # Extract text from the PDF
                    with open(temp_path, 'rb') as file:
                        reader = PyPDF2.PdfReader(file)
                        for page_num in range(len(reader.pages)):
                            content += reader.pages[page_num].extract_text() + "\n"
                    
                    # Clean up the temporary file
                    os.unlink(temp_path)
                    
                    if content and len(content) > 100:
                        print("Successfully extracted PDF content directly!")
                    else:
                        print("Direct PDF extraction returned insufficient content, falling back to Firecrawl")
                        content = ""
                else:
                    print("Failed to download PDF, falling back to Firecrawl")
            except Exception as pdf_error:
                print(f"Error in direct PDF extraction: {str(pdf_error)}")
                content = ""
        
        # If direct extraction failed or PyPDF2 is not available, fall back to Firecrawl
        if not content or len(content) < 100:
            print("Using Firecrawl to extract content...")
            app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
            response = app.scrape_url(url=pdf_link)
            
            # Try to get content from different response fields
            content = response.get("markdown", "")
            if not content or len(content) < 100:
                content = response.get("text", "")
            if not content or len(content) < 100:
                content = response.get("html", "")
        
        # Check if we got any usable content
        if not content or len(content) < 100 or content.startswith("%PDF"):
            print("Warning: Resume content is empty, too short, or contains raw PDF data!")
            return "Failed to extract resume content - received raw PDF data instead of text"
            
        # Clean up the content
        content = content.replace("\u00a0", " ")  # Replace non-breaking spaces
        content = content.replace("\u2022", "- ")  # Replace bullets
        content = "\n".join([line.strip() for line in content.split("\n")])  # Clean up whitespace
        
        print(f"Successfully extracted resume content ({len(content)} characters)")
        print("\n==== RESUME CONTENT PREVIEW ====")
        print(content[:500] + "..." if len(content) > 500 else content)
        print("==== END OF RESUME PREVIEW ====")
        return content
    except Exception as e:
        print(f"Error parsing resume: {str(e)}")
        return f"Error parsing resume: {str(e)}"


class JobScraper:
    def __init__(self):
        self.app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

    async def parse_resume(self, pdf_link: str) -> str:
        """Parse a resume from a PDF link."""
        return _cached_parse_resume(pdf_link)
        
    async def scrape_job_postings(self, source_urls: list[str]) -> list[Job]:
        """Scrape job postings from multiple sources."""
        all_jobs = []
        
        for source_url in source_urls:
            try:
                print(f"Scraping job listings from: {source_url}")
                # Get the main content from the job board
                response = self.app.scrape_url(url=source_url)
                content = response.get("markdown", "")
                
                # Use OpenAI to extract individual job listings
                extract_prompt = f"""Extract all individual job listings from this job board page. 
                For each job, provide:
                1. Job title
                2. Company name
                3. Job URL (if available, or construct it from the job ID and base URL)
                
                Job Board Content:
                {content[:15000]}  # Limiting content length to avoid token issues
                
                Return the results as a JSON array of objects with fields: title, company, url
                Example: [{{
                    "title": "Senior Software Engineer",
                    "company": "Acme Corp",
                    "url": "https://example.com/jobs/12345"
                }}, ...]
                """
                
                import openai
                import os
                import json
                
                openai.api_key = os.getenv("OPENAI_API_KEY")
                extract_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": extract_prompt}],
                    temperature=0
                )
                
                # Parse the response
                extracted_text = extract_response.choices[0].message.content
                # Clean up the response to ensure it's valid JSON
                extracted_text = extracted_text.strip()
                if extracted_text.startswith("```json"):
                    extracted_text = extracted_text[7:]
                if extracted_text.endswith("```"):
                    extracted_text = extracted_text[:-3]
                extracted_text = extracted_text.strip()
                
                try:
                    # Parse the JSON response
                    job_listings = json.loads(extracted_text)
                    
                    # Process each job listing
                    for job_data in job_listings:
                        # Ensure URL is absolute
                        job_url = job_data.get("url", "")
                        if job_url and not (job_url.startswith("http://") or job_url.startswith("https://")):
                            # Handle relative URLs
                            from urllib.parse import urljoin
                            job_url = urljoin(source_url, job_url)
                        
                        # Create job object
                        job = Job(
                            title=job_data.get("title", f"Job at {job_data.get('company', 'Unknown')}"),
                            company=job_data.get("company", "Unknown Company"),
                            url=job_url or source_url  # Fallback to source URL if no specific URL found
                        )
                        
                        # Add to our list
                        all_jobs.append(job)
                    
                    print(f"Extracted {len(job_listings)} job listings from {source_url}")
                    
                except json.JSONDecodeError as e:
                    print(f"Error parsing job listings JSON: {str(e)}")
                    # Fallback: create a single job entry for the entire page
                    domain = source_url.split('//')[1].split('/')[0]
                    company = domain.split('.')[-2].capitalize()
                    
                    job = Job(
                        title=f"Jobs at {company}",
                        company=company,
                        url=source_url
                    )
                    all_jobs.append(job)
                    
            except Exception as e:
                print(f"Error scraping {source_url}: {str(e)}")
        
        return all_jobs

    async def scrape_job_content(self, job_url: str) -> str:
        """Scrape the content of a specific job posting."""
        try:
            response = self.app.scrape_url(url=job_url)
            return response.get("markdown", f"Job posting from {job_url}")
        except Exception as e:
            print(f"Error scraping job content from {job_url}: {str(e)}")
            return f"Could not retrieve job details from {job_url}"
