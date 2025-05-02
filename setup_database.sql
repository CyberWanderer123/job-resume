-- Create the job_sources table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.job_sources (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    last_checked TIMESTAMP WITH TIME ZONE
);

-- Add indexes for better performance
CREATE INDEX IF NOT EXISTS idx_job_sources_url ON public.job_sources(url);
