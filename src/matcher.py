from typing import Dict
import json
import openai
import os
import re

class JobMatcher:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        openai.api_key = self.api_key

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Truncate text to a maximum character count while preserving important parts."""
        if len(text) <= max_chars:
            return text
            
        # If we need to truncate, keep the beginning and end which often contain the most relevant info
        # For resumes, the beginning often has personal info and recent experience
        # The end often has education and skills
        half_length = max_chars // 2
        return text[:half_length] + "\n[...content truncated...]\n" + text[-half_length:]
    
    def _estimate_tokens(self, text: str) -> int:
        """Roughly estimate the number of tokens in a text (1 token ≈ 4 chars in English)."""
        return len(text) // 4
        
    async def evaluate_match(self, resume: str, job_posting: str) -> Dict:
        """Evaluate if a candidate is a good fit for a job."""
        # Limit the size of inputs to avoid token limit errors
        # GPT-4 has an 8k token context limit, so we'll aim to keep our inputs under ~6k tokens
        # to leave room for the response and system message
        max_total_tokens = 6000
        
        # Estimate current tokens
        resume_tokens = self._estimate_tokens(resume)
        job_tokens = self._estimate_tokens(job_posting)
        
        # If we're over the limit, truncate both proportionally
        if resume_tokens + job_tokens > max_total_tokens:
            print(f"Truncating inputs to fit token limit. Original sizes - Resume: {resume_tokens}, Job: {job_tokens}")
            # Calculate how much we need to reduce
            reduction_factor = max_total_tokens / (resume_tokens + job_tokens)
            # Apply reduction proportionally
            max_resume_chars = int(len(resume) * reduction_factor)
            max_job_chars = int(len(job_posting) * reduction_factor)
            
            resume = self._truncate_text(resume, max_resume_chars)
            job_posting = self._truncate_text(job_posting, max_job_chars)
            
            print(f"Truncated sizes - Resume: {self._estimate_tokens(resume)}, Job: {self._estimate_tokens(job_posting)}")
        
        # Extract key information from resume first
        try:
            print(f"\n==== RESUME TEXT BEING ANALYZED (FIRST 500 CHARS) ====")
            print(resume[:500] + "..." if len(resume) > 500 else resume)
            print(f"==== END OF RESUME PREVIEW (TOTAL LENGTH: {len(resume)} chars) ====")
            
            # Pre-process resume to highlight skills section
            # Look for common skills section headers and highlight them
            skills_section_markers = [
                "SKILLS", "TECHNICAL SKILLS", "TECHNOLOGIES", "CORE COMPETENCIES", 
                "EXPERTISE", "PROFICIENCIES", "TECHNICAL EXPERTISE", "TOOLS"
            ]
            
            highlighted_resume = resume
            for marker in skills_section_markers:
                highlighted_resume = highlighted_resume.replace(f"{marker}:", f">>>SKILLS_SECTION<<< {marker}:")
                highlighted_resume = highlighted_resume.replace(f"{marker.title()}:", f">>>SKILLS_SECTION<<< {marker.title()}:")
                highlighted_resume = highlighted_resume.replace(f"{marker.upper()}:", f">>>SKILLS_SECTION<<< {marker.upper()}:")
            
            print("\n==== HIGHLIGHTED RESUME SECTIONS ====")
            print(highlighted_resume[:1000] + "..." if len(highlighted_resume) > 1000 else highlighted_resume)
            print("==== END OF HIGHLIGHTED RESUME ====")
            
            # Use a more focused prompt with explicit instructions for skill extraction
            extract_prompt = f"""You are an expert resume analyzer with deep knowledge of the tech industry. Your primary task is to extract ALL skills from this resume.
            
            Resume content:
            {highlighted_resume}
            
            CRITICAL INSTRUCTIONS:
            1. Pay special attention to any sections marked with >>>SKILLS_SECTION<<< as they contain important skills
            2. Look for technical skills throughout the ENTIRE resume, including in project descriptions and work experience
            3. Extract ALL programming languages, frameworks, tools, platforms, and technologies mentioned ANYWHERE in the resume
            4. Be THOROUGH and COMPREHENSIVE - do not miss any skills mentioned in the resume
            5. After extracting explicit skills, infer related skills that would be necessary for the mentioned projects and roles
            
            For example, if you see:
            - React -> also infer JavaScript, HTML, CSS, Git
            - Machine Learning -> also infer Python, data analysis
            - AWS -> also infer cloud deployment, infrastructure
            
            Return a JSON object with these fields:
            {{
                "ExplicitSkills": [COMPREHENSIVE list of ALL technical skills explicitly mentioned ANYWHERE in the resume],
                "InferredSkills": [list of related skills that can be reasonably inferred from experience and projects],
                "Experience": [list of work experiences in format "Company - Title (Time Period)" or as much info as available],
                "Education": [list of education items],
                "YearsOfExperience": estimated total years or "Unknown" if unclear,
                "ProjectTypes": [types of projects the candidate has worked on, like "Web Applications", "Mobile Apps", etc.]
            }}
            
            Format your response as valid JSON only. No explanations, just the JSON.
            """
            
            print("Sending resume to OpenAI for analysis...")
            extract_response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": extract_prompt}],
                temperature=0
            )
            
            resume_analysis = extract_response.choices[0].message.content.strip()
            print(f"\n==== RAW MODEL RESPONSE ====")
            print(resume_analysis)
            print("==== END OF RAW RESPONSE ====")
            # Clean up the response to ensure it's valid JSON
            resume_analysis = resume_analysis.strip()
            
            # Handle various ways the model might format JSON
            if resume_analysis.startswith("```json"):
                resume_analysis = resume_analysis[7:]
            elif resume_analysis.startswith("```"):
                resume_analysis = resume_analysis[3:]
                
            if resume_analysis.endswith("```"):
                resume_analysis = resume_analysis[:-3]
                
            # Remove any additional text before or after the JSON
            try:
                # Find the first '{' and the last '}'
                start_idx = resume_analysis.find('{')
                end_idx = resume_analysis.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    resume_analysis = resume_analysis[start_idx:end_idx+1]
            except Exception as e:
                print(f"Error cleaning JSON: {str(e)}")
                
            resume_analysis = resume_analysis.strip()
            
            # Try to validate and pretty-print the JSON
            try:
                # First try direct JSON parsing
                try:
                    parsed_json = json.loads(resume_analysis)
                except json.JSONDecodeError:
                    # Try to extract JSON from text if it's surrounded by other text
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', resume_analysis)
                    if json_match:
                        json_str = json_match.group(0)
                        parsed_json = json.loads(json_str)
                    else:
                        raise json.JSONDecodeError("No JSON object found", resume_analysis, 0)
                
                # Pretty print the parsed JSON
                resume_analysis = json.dumps(parsed_json, indent=2)
                print("\n==== PARSED RESUME CONTENT ====")
                print(resume_analysis)
                print("==== END OF RESUME CONTENT ====")
                print("Successfully parsed resume JSON")
                
                # Check if we got empty fields
                if not parsed_json.get("ExplicitSkills") or len(parsed_json.get("ExplicitSkills", [])) == 0:
                    print("WARNING: No explicit skills were extracted from the resume!")
                    # Add fallback skill extraction using common tech keywords
                    print("Attempting fallback skill extraction...")
                    tech_keywords = [
                        "Python", "JavaScript", "TypeScript", "Java", "C#", "C++", "Go", "Ruby", "PHP", "Swift",
                        "React", "Angular", "Vue", "Node.js", "Express", "Django", "Flask", "Spring", "ASP.NET",
                        "HTML", "CSS", "SASS", "LESS", "Bootstrap", "Tailwind", "Material UI",
                        "AWS", "Azure", "GCP", "Firebase", "Heroku", "Netlify", "Vercel",
                        "Docker", "Kubernetes", "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI",
                        "SQL", "MySQL", "PostgreSQL", "MongoDB", "DynamoDB", "Redis", "Elasticsearch",
                        "REST API", "GraphQL", "WebSockets", "gRPC",
                        "Git", "GitHub", "GitLab", "Bitbucket",
                        "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
                        "Agile", "Scrum", "Kanban", "Jira", "Confluence"
                    ]
                    
                    extracted_skills = []
                    for keyword in tech_keywords:
                        if keyword.lower() in resume.lower():
                            extracted_skills.append(keyword)
                    
                    if extracted_skills:
                        print(f"Found {len(extracted_skills)} skills via fallback method: {extracted_skills}")
                        parsed_json["ExplicitSkills"] = extracted_skills
                    else:
                        print("No skills found even with fallback method")
                        
                if not parsed_json.get("Experience") or len(parsed_json.get("Experience", [])) == 0:
                    print("WARNING: No experience was extracted from the resume!")
                    
            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse resume JSON: {str(e)}")
                print("\n==== RAW RESUME RESPONSE (FAILED TO PARSE) ====")
                print(resume_analysis[:1000] + "..." if len(resume_analysis) > 1000 else resume_analysis)
                print("==== END OF RAW RESUME RESPONSE ====")
                
                # Create a basic JSON structure if parsing failed
                print("Creating fallback JSON structure...")
                
                # Extract skills using the fallback keyword method
                tech_keywords = [
                    "Python", "JavaScript", "TypeScript", "Java", "C#", "C++", "Go", "Ruby", "PHP", "Swift",
                    "React", "Angular", "Vue", "Node.js", "Express", "Django", "Flask", "Spring", "ASP.NET",
                    "HTML", "CSS", "SASS", "LESS", "Bootstrap", "Tailwind", "Material UI",
                    "AWS", "Azure", "GCP", "Firebase", "Heroku", "Netlify", "Vercel",
                    "Docker", "Kubernetes", "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI",
                    "SQL", "MySQL", "PostgreSQL", "MongoDB", "DynamoDB", "Redis", "Elasticsearch",
                    "REST API", "GraphQL", "WebSockets", "gRPC",
                    "Git", "GitHub", "GitLab", "Bitbucket",
                    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
                    "Agile", "Scrum", "Kanban", "Jira", "Confluence"
                ]
                
                extracted_skills = []
                for keyword in tech_keywords:
                    if keyword.lower() in resume.lower():
                        extracted_skills.append(keyword)
                
                if not extracted_skills:
                    extracted_skills = ["Unable to parse skills"]
                
                resume_analysis = json.dumps({
                    "ExplicitSkills": extracted_skills,
                    "InferredSkills": ["Git", "GitHub", "CI/CD", "Agile", "REST APIs"],  # Common skills most developers have
                    "Experience": ["Unable to parse experience"],
                    "Education": ["Unable to parse education"],
                    "YearsOfExperience": "Unknown",
                    "ProjectTypes": ["Software Development"]
                }, indent=2)
            
            # Now use this structured information for matching with enhanced contextual understanding
            prompt = f"""You are an expert job recruiter with decades of experience matching candidates to positions.
            
            CANDIDATE PROFILE (from resume analysis):
            {resume_analysis}
            
            JOB POSTING:
            {job_posting}
            
            Your task is to determine if this candidate is a good match for this job:
            
            1. First, identify the key skills and requirements from the job posting
            2. Compare these with BOTH the candidate's explicit skills AND inferred skills
            3. Consider the candidate's project types and experience level
            4. Make a balanced assessment based on all available information
            
            IMPORTANT GUIDELINES:
            - Use both explicit AND inferred skills when evaluating the match
            - Consider the candidate's project experience - someone who has built similar projects likely has the necessary skills
            - Be reasonable about skill gaps - focus on core requirements, not every single mentioned technology
            - For frontend developers, assume familiarity with Git, GitHub, UI/UX principles, and common development tools
            - For backend developers, assume familiarity with databases, API design, and server management
            - For full-stack developers, assume familiarity with deployment, CI/CD concepts, and end-to-end application development
            - IMPORTANT: Use a LOWER threshold for matching - a score of 50% or higher should be considered a match
            - Be optimistic about the candidate's ability to learn new skills quickly
            
            Return your analysis in this JSON format:
            {{
                "is_match": true/false (set to true if match_percentage >= 50),
                "match_percentage": number between 0-100,
                "matching_skills": [skills from the candidate that match job requirements, including both explicit and inferred skills],
                "missing_skills": [important core skills/requirements the candidate truly lacks],
                "reason": "clear explanation of your decision that considers both explicit and inferred skills"
            }}
            
            If you can't properly analyze the match due to missing information, set is_match to false and explain why in the reason field.
            """
        except Exception as e:
            print(f"Error in resume pre-processing: {str(e)}")
            # Fallback to simpler prompt if pre-processing fails
            prompt = f"""You are an expert job interviewer with decades of experience. Analyze the resume and job posting to determine if the candidate is a good fit. Be critical in your assessment and accept only applicants that meet at least 75% of the requirements.
            
            Resume:
            {resume}
            
            Job Posting:
            {job_posting}
            
            Determine if this candidate is a good fit and explain why briefly.
            Return your response in JSON format with the following structure:
            {{
                "is_match": true/false,
                "reason": "brief explanation of why the candidate is or isn't a good fit"
            }}
            """
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert job interviewer. Be extremely critical and only recommend jobs that are a very strong match for the candidate's specific skills and experience."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            
            content = response.choices[0].message.content
            print("\nRaw response from model:")
            print(content[:500] + "..." if len(content) > 500 else content)
            
            # Clean up the response to ensure it's valid JSON
            cleaned_content = content.strip()
            
            # Handle various ways the model might format JSON
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            elif cleaned_content.startswith("```"):
                cleaned_content = cleaned_content[3:]
                
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
                
            # Remove any additional text before or after the JSON
            try:
                # Find the first '{' and the last '}'
                start_idx = cleaned_content.find('{')
                end_idx = cleaned_content.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    cleaned_content = cleaned_content[start_idx:end_idx+1]
            except Exception as e:
                print(f"Error cleaning JSON: {str(e)}")
                
            cleaned_content = cleaned_content.strip()
            
            # Extract JSON from the response
            try:
                result = json.loads(cleaned_content)
                print("Successfully parsed job matching result")
                return result
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                print(f"Problematic content: {cleaned_content[:200]}...")
                
                # Try a more aggressive approach - look for any JSON-like structure
                try:
                    # Look for patterns like {"is_match": true, ...}
                    import re
                    json_pattern = r'\{[^\{\}]*"is_match"\s*:\s*(true|false)[^\{\}]*\}'
                    match = re.search(json_pattern, content, re.IGNORECASE)
                    
                    if match:
                        potential_json = match.group(0)
                        print(f"Found potential JSON: {potential_json}")
                        result = json.loads(potential_json)
                        print("Successfully parsed with regex approach")
                        return result
                except Exception as inner_e:
                    print(f"Regex parsing also failed: {str(inner_e)}")
                
                # If we got here, all parsing attempts failed
                # Create a simple result based on keywords in the response
                is_match = False
                if "match" in content.lower() and ("good fit" in content.lower() or "strong match" in content.lower()):
                    is_match = True
                    
                reason = "Could not parse structured response. "
                if is_match:
                    reason += "Based on keywords, this appears to be a match."
                else:
                    reason += "Based on keywords, this does not appear to be a match."
                    
                return {
                    "is_match": is_match,
                    "match_percentage": 75 if is_match else 30,
                    "matching_skills": [],
                    "missing_skills": [],
                    "reason": reason
                }
        except Exception as e:
            print(f"Error calling OpenAI API: {str(e)}")
            return {
                "is_match": False,
                "reason": f"Error evaluating match: {str(e)}"
            }
