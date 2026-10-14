# Tencent requirements and approved model configuration

Checked against official public information on 29 September 2026. Exact mandatory service minima remain **unconfirmed**; deployment/submission must not claim organizer confirmation based on this document.

The [official Tencent Cloud Hackathon site](https://tch.tencentcloud.com/) positions the event around building agentic AI with Tencent products, including CodeBuddy and WorkBuddy. The [official developer manual page](https://tch.tencentcloud.com/developerManual) did not provide an actionable service checklist when reviewed. The [Tencent-hosted event listing](https://luma.com/26fqf3hy) identifies the tracks and Tencent tools. None of these establishes the precise minimum service combination for this team's Aspire submission.

**Answered by the official Hackathon Handbook** (`AI CAN DO IT Tencent Cloud AI Singapore Hackathon 2026 Handbook.pdf`, 42 pages, distributed to registered teams; read 15 Oct 2026):

- **Mandatory:** "The project must be original and built on at least one of the products CodeBuddy or WorkBuddy. Proof of product usage is mandatory: chat screenshots, API call logs, or a written development-process description. Without proof, the project will not proceed to scoring." The submission form requires at least 3 CodeBuddy/WorkBuddy chat screenshots or a screen recording (section 8).
- **Not mandatory:** Hunyuan, ADP, Agent Runtime, TRTC and other Tencent Cloud services appear only under "Suggested Tools" (section 7).
- **Required submission items:** project title, short blurb (under 10 words), project description (overview, real-world insights, business and technical architecture "and how prompts drive the AI generation", business value), the CodeBuddy/WorkBuddy history, a 16:9 cover image (380x216 recommended).
- **Optional:** a 5 to 8 minute demo video (must include a reflection on the build approach with CodeBuddy/WorkBuddy tips) and a live URL (bonus points).
- **Aspire brief deliverables:** a worked example per scenario, a live demo walkthrough, an architecture and trust-boundary diagram with key design trade-offs, and complete source on GitHub. State the chosen case study at the start of the presentation.
- **Judging:** preliminary technical judging by Aspire and Tencent Cloud experts (track criteria shared after registration); Demo Day scores ten 10-point dimensions, including **AI Interaction** ("quality and depth of AI usage") and **Responsible AI & Ethics**.

Note on the model: Hunyuan is not required, but the Aspire brief describes "an LLM reasoning layer on top" and the rubric scores AI Interaction. Answering in extractive mode only is safe and accurate, but a live model run strengthens both.

## Model setup

The [official Hunyuan compatibility documentation](https://cloud.tencent.com/document/product/1729/111007) documents a chat-completions-compatible endpoint with bearer API-key authentication. It also carries a notice about newer services moving to TokenHub. Use the base URL and model ID enabled for the team's approved account; do not assume a legacy example model is provisioned or currently offered.

The generic adapter accepts approved compatible services through `.env`:

```
IB_LLM_PROVIDER=openai_compatible
IB_LLM_REQUIRE_LIVE=1
IB_LLM_BASE_URL=YOUR_APPROVED_PROVIDER_BASE_URL
IB_LLM_MODEL=YOUR_APPROVED_MODEL_ID
IB_LLM_API_KEY=YOUR_APPROVED_MODEL_KEY
IB_LLM_INPUT_PER_MILLION=
IB_LLM_OUTPUT_PER_MILLION=
IB_LLM_CURRENCY=USD
```

The final three fields describe actual account pricing, if known. Currency and token prices are not assumed to be Tencent prices. Unknown usage/rates produce a null estimate. Run the live evaluator after configuration and retain the report. It uses fictional Company A evidence, not a real enterprise corpus. With the current placeholder configuration its report correctly says **not run**.
