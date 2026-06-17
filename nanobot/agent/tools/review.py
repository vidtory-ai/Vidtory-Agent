"""Review/Reflexion tool for self-correction."""

from typing import Any
from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import StringSchema, tool_parameters_schema
from loguru import logger

@tool_parameters(
    tool_parameters_schema(
        draft_content=StringSchema("The content of your draft response to evaluate."),
        required=["draft_content"],
    )
)
class ReviewDraftTool(Tool):
    """Review a drafted response for quality and completeness.
    
    You MUST call this tool before responding to the user.
    """

    @classmethod
    def create(cls, ctx: Any) -> "ReviewDraftTool":
        tool = cls()
        tool.ctx = ctx
        return tool

    @property
    def name(self) -> str:
        return "review_draft"

    @property
    def description(self) -> str:
        return (
            "Review your draft response before sending it to the user. "
            "You MUST use this tool to evaluate your answer for completeness, "
            "accuracy, and formatting. If the draft is perfect, it will return [PERFECT]. "
            "If not, it will return constructive feedback on what to improve."
        )

    async def execute(self, draft_content: str, **kwargs: Any) -> str:
        # Keep track of reflexion attempts via TurnContext session
        session = getattr(self.ctx, "session", None)
        if session and session.metadata:
            attempts = session.metadata.get("reflexion_attempts", 0)
            if attempts >= 3:
                return "[PERFECT] Maximum review attempts reached. You may now output this draft directly to the user."
            session.metadata["reflexion_attempts"] = attempts + 1
        else:
            logger.warning("No session metadata found for Reflexion tracking.")

        logger.info(f"Reflexion Tool called. Analyzing draft...")
        
        # We enforce a self-reflection prompt
        return (
            f"DRAFT SAVED FOR INTERNAL REVIEW.\n\n"
            f"Review the draft you just submitted:\n"
            f"-----------\n{draft_content}\n-----------\n\n"
            f"Evaluate it objectively based on the user's requirements. "
            f"Does it fully satisfy the user's request with high quality? "
            f"If YES, your next response MUST just output the draft to the user exactly as is. "
            f"If NO, your next response MUST be an improved version of the draft."
        )
