# Experimentation Platform Engineer Take-Home Assessment

## Overview
Build a simplified experimentation API that demonstrates your ability to work with the core technologies and concepts in our stack. You may use AI tools to assist with implementation.

## The Challenge
Create a basic A/B testing API service that allows:
- Creating experiments with multiple variants
- Assigning users to experiment variants
- Recording experiment events/conversions
- Retrieving experiment performance data

## Technical Requirements

### API Endpoints
Build a Python REST API with these endpoints:

**POST /experiments** - Create a new experiment

**GET /experiments/{id}/assignment/{user_id}** - Get user's variant assignment
- Must be idempotent: once a user receives a variant assignment for an experiment, all subsequent calls must return the same assignment
- Assignments should be stored persistently
- Assignment logic should support configurable traffic allocation percentages per variant

**POST /events** - Record events
- Events must include at minimum: user_id, type (e.g., "click", "purchase", "signup"), timestamp, and properties (flexible JSON object for additional context)

**GET /experiments/{id}/results** - Get experiment performance summary
- Only count events that occur AFTER a user's assignment timestamp
- Design a flexible reporting structure that supports various types of analysis
- Consider what query parameters would enable different views of the data (e.g., time ranges, event types, aggregation levels)
- Think creatively about how to structure the response to support different use cases (real-time monitoring, deep analysis, executive summaries, etc.)
- Your design should demonstrate understanding of what stakeholders need from experiment results

### Authentication
- All endpoints must be protected with Bearer token authentication
- Validate tokens against an internal list (can be configuration-based or in-memory)
- Return appropriate HTTP status codes for authentication failures

### Data Layer
- Use any database you prefer (SQLite is fine for simplicity)
- Design a schema that supports experiments, variants, user assignments, and events
- Consider appropriate indexes for common query patterns

### Infrastructure
- Provide a simple deployment configuration (Docker, docker-compose, or basic AWS CDK)
- Include basic environment configuration and dependency management

## Deliverables

1. **Working code with clear setup instructions**
   - All source code
   - README with setup and running instructions
   - Requirements/dependencies file

2. **Brief documentation (15-20 minutes)**
   - Architecture decisions and trade-offs
   - How you'd extend this for production scale
   - One improvement you'd prioritize next
   - Explanation of your results endpoint design philosophy and choices

3. **Example usage**
   - Simple script or curl commands demonstrating all API endpoints
   - Include examples showing idempotent assignment behavior

## Evaluation Criteria
- **Code quality**: Clean, readable Python with appropriate error handling
- **API design**: RESTful principles and practical usability
- **Data modeling**: Logical schema design and query efficiency
- **Problem-solving**: How you handle edge cases and constraints
- **Communication**: Clear documentation of decisions and trade-offs
- **Number of additional features implemented**

## Additional Features (Optional)
- Statistical significance calculation for experiment results
- Basic feature flagging capability
- Simple caching strategy
- Unit tests for critical paths
- Creative metrics or analysis features in the results endpoint

## Submission
Please submit via GitHub repository or zip file, including:
- All source code
- README with setup instructions
- Brief design document (can be markdown in repo)
- Example usage scripts/commands
