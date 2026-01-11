"""
OpenAI Cover Letter Generator

Generates personalized cover letters for Upwork job applications using OpenAI's API.
Handles API communication, prompt formatting, and cover letter storage.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import openai
import aiofiles

from .config import get_config
from .utils import save_json_async, load_json_async, sanitize_filename, ensure_directories

logger = logging.getLogger(__name__)

class CoverLetterGenerator:
    """Handles generation of cover letters using OpenAI API"""
    
    def __init__(self):
        """Initialize the generator with configuration"""
        self.config = get_config()
        self.openai_config = self.config.get_openai_config()
        self.cover_letter_config = self.config.get_cover_letter_config()
        self.storage_config = self.config.get_storage_config()
        
        # Initialize OpenAI client
        self.client = openai.AsyncOpenAI(
            api_key=self.openai_config['api_key']
        )
        
        logger.info("Cover letter generator initialized")
    
    def _create_prompt(self, job_description: str, custom_prompt: Optional[str] = None) -> str:
        """
        Create prompt for OpenAI API
        
        Args:
            job_description: The job posting description
            custom_prompt: Optional custom prompt template
        
        Returns:
            Formatted prompt string
        """
        if custom_prompt:
            template = custom_prompt
        else:
            template = self.cover_letter_config.get(
                'template',
                "Write a professional cover letter for this Upwork job posting:\n\n{job_description}"
            )
        
        # Format the template with job description
        prompt = template.format(job_description=job_description)
        
        # Add additional instructions
        additional_instructions = [
            "Keep the cover letter concise and professional.",
            "Highlight relevant skills and experience.",
            "Show enthusiasm for the project.",
            "Include a call to action.",
            "Do not include placeholder information like [Your Name] or [Date].",
            "Make it personalized to the specific job requirements."
        ]
        
        max_length = self.cover_letter_config.get('max_length', 500)
        prompt += f"\n\nAdditional requirements:\n"
        prompt += f"- Maximum length: approximately {max_length} words\n"
        prompt += "- " + "\n- ".join(additional_instructions)
        
        return prompt
    
    async def generate_cover_letter(self, job_description: str, 
                                  custom_prompt: Optional[str] = None,
                                  max_retries: int = 3) -> Optional[str]:
        """
        Generate cover letter using OpenAI API
        
        Args:
            job_description: The job posting description
            custom_prompt: Optional custom prompt template
            max_retries: Maximum number of API retries
        
        Returns:
            Generated cover letter text or None if failed
        """
        for attempt in range(max_retries):
            try:
                # Create prompt
                prompt = self._create_prompt(job_description, custom_prompt)
                
                logger.info(f"Generating cover letter (attempt {attempt + 1}/{max_retries})")
                logger.debug(f"Prompt: {prompt[:200]}...")
                
                # Call OpenAI API
                response = await self.client.chat.completions.create(
                    model=self.openai_config.get('model', 'gpt-3.5-turbo'),
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional freelancer writing cover letters for Upwork job applications. Write compelling, personalized cover letters that highlight relevant skills and experience."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=self.openai_config.get('max_tokens', 1000),
                    temperature=self.openai_config.get('temperature', 0.7)
                )
                
                # Extract generated text
                cover_letter = response.choices[0].message.content.strip()
                
                # Log token usage
                usage = response.usage
                logger.info(
                    f"Cover letter generated successfully. "
                    f"Tokens used: {usage.total_tokens} "
                    f"(prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens})"
                )
                
                # Validate generated content
                if len(cover_letter) < 50:
                    logger.warning("Generated cover letter is too short")
                    if attempt < max_retries - 1:
                        continue
                
                return cover_letter
                
            except openai.APIError as e:
                logger.error(f"OpenAI API error (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Unexpected error generating cover letter (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
        
        return None
            
        except Exception as e:
            logger.error(f"Error getting cover letter path for job {job_id}: {e}")
            return None

# Convenience functions for external use
async def generate_cover_letter_for_job(job_data: Dict[str, Any], 
                                       custom_prompt: Optional[str] = None) -> Optional[str]:
    """
    Generate cover letter for a job (convenience function)
    
    Args:
        job_data: Job data dictionary
        custom_prompt: Optional custom prompt template
    
    Returns:
        File path if successful, None otherwise
    """
    generator = CoverLetterGenerator()
    return await generator.generate_and_save_cover_letter(job_data, custom_prompt)

if __name__ == "__main__":
    # Test the cover letter generator
    async def test_generator():
        try:
            # Sample job data for testing
            job_data = {
                "id": "test_job_123",
                "title": "Python Developer Position",
                "description": "We are looking for a skilled Python developer to join our team..."
            }
            
            generator = CoverLetterGenerator()
            cover_letter = await generator.generate_cover_letter(job_data['description'])
            
            if cover_letter:
                print(f"Generated cover letter:\n{cover_letter}")
                
                # Save the cover letter
                file_path = await generator.save_cover_letter(
                    job_data['id'], 
                    cover_letter, 
                    job_data['title']
                )
                
                if file_path:
                    print(f"Cover letter saved to: {file_path}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    import asyncio
    asyncio.run(test_generator())
