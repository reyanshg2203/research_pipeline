import anthropic
from dotenv import load_dotenv #reads env file with API 
import os
import json
import sys
sys.path.append("..")  #gets schema from another folder
from schema import ProblemSchema

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Load lesson content 
with open("../lessons/lesson_01.txt", "r") as f:
    lesson_content = f.read()

    
#prompt (to be refined), states attributes explicitly for now
prompt = f"""You are a math problem designer for a 10th grade geometry class.

Below is content from a lesson on dilations and scale drawings:

<lesson>
{lesson_content}
</lesson>

Your job is to invent ONE original math problem based on this lesson and represent it as a structured JSON object. Do not copy problems from the lesson. The problem must have a single numerical or yes/no answer.

Rules:
1. Only use mathematical concepts explicitly taught in this lesson
2. The problem must be solvable using only words and numbers — no diagrams
3. All declared values must be internally consistent
4. The target must be uniquely determinable from the declared facts
5. Use null for any unknown values
6. The relationship type must be one of the allowed enum values

CRITICAL — Naming conventions (these must be followed exactly):
- Triangle ids: use bare letters ONLY. Write "ABC" — NOT "triangle_ABC", NOT "triangleABC", NOT "Triangle ABC"
- Polygon ids: use bare letters ONLY. Write "ABCD" — NOT "polygon_ABCD"
- Segment ids: use bare letters ONLY. Write "AB" — NOT "segment_AB"
- Point ids: use single capital letters or letters with primes. Write "A" or "A'" — NOT "point_A"
- Line ids: use lowercase single letters. Write "m" or "n" — NOT "line_m"
- Circle ids: use single lowercase letters. Write "c" — NOT "circle_c"
- Target attribute uses dot notation: "sides.AB", "angles.A", "length", "radius"

CRITICAL — Entity declaration rules:
- Only declare an entity if it has a role INDEPENDENT of being part of another entity
- DO NOT declare points A, B, C as separate Point entities just because they are vertices of triangle ABC. Vertices are implicit in the triangle.
- DO NOT declare side AB as a separate Segment entity just because it is a side of triangle ABC. Sides are implicit in the triangle.
- DO declare a point as a separate Point entity if it serves a special role like a dilation center, intersection point, or center of a circle
- DO declare a segment as a separate Segment entity if it has properties that don't belong to any single polygon — like a midsegment, an altitude, or a transversal

CRITICAL — Attribute keys (DO NOT invent new keys):
Only use the keys listed below for each relationship type. Do not add extra keys for explanations, descriptions, or context. If a relationship has no required attributes, use an empty dictionary.

similar_AA, similar_SAS, similar_SSS, similar_unspecified:
  scale_factor (float or null), pre_image (str), image (str), congruent_angle_pairs (list of [str, str])

dilation:
  scale_factor (float), center (str or null), pre_image (str), image (str)

scaled_copy, scaled_copy_unspecified:
  scale_factor (float or null), pre_image (str), image (str)

proportional_segments:
  ratio (float)

midsegment_ratio:
  ratio (always 0.5)

triangle_proportionality:
  parallel_side (str), segment1 (str), segment2 (str)

altitude_to_hypotenuse:
  altitude_id (str), hypotenuse (str), segment1 (str), segment2 (str)

geometric_mean_altitude:
  altitude_id (str), segment1 (str), segment2 (str)

geometric_mean_leg:
  leg_id (str), hypotenuse (str), adjacent_segment (str)

transversal_cut:
  transversal (str), line1 (str), line2 (str)

congruent_angles, congruent_segments:
  ids (list of str)

congruent_triangles:
  pre_image (str), image (str), criterion (str)

collinear_dilation:
  center (str), pre_image_point (str), image_point (str)

All other relationship types use an empty attributes dictionary."""

#API Call - Haiku 4.5, forcing use  of tool for structured schema format 
message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1000,
    messages=[
        {"role": "user", "content": prompt}
    ],
    tools=[ 
        {
            "name": "generate_problem",
            "description": "Generate a geometry problem in structured schema format",
            "input_schema": ProblemSchema.model_json_schema()
        }
    ],
    tool_choice={"type": "tool", "name": "generate_problem"}
)

# Extract the tool use block, avoiding all the Haiku noise in other blocks
tool_use = None

for block in message.content:
    if block.type == "tool_use":
        tool_use = block
        break
raw = tool_use.input

print("Raw output from Haiku:")
print(json.dumps(raw, indent=2)) #convert from dictionary 

# Validate with Pydantic
try:
    validated = ProblemSchema(**raw)
    print("\nPydantic validation passed")
    
    # Save to outputs
    with open("../outputs/schema_lesson_01.json", "w") as f:
        json.dump(raw, f, indent=2)
    print("Saved to outputs/schema_lesson_01.json")

except Exception as e:
    print(f"\nPydantic validation failed: {e}")
