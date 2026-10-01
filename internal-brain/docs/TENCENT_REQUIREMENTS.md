# Tencent requirements and approved model configuration

Checked against official public information on 29 September 2026. Exact mandatory service minima remain **unconfirmed**; deployment/submission must not claim organizer confirmation based on this document.

The [official Tencent Cloud Hackathon site](https://tch.tencentcloud.com/) positions the event around building agentic AI with Tencent products, including CodeBuddy and WorkBuddy. The [official developer manual page](https://tch.tencentcloud.com/developerManual) did not provide an actionable service checklist when reviewed. The [Tencent-hosted event listing](https://luma.com/26fqf3hy) identifies the tracks and Tencent tools. None of these establishes the precise minimum service combination for this team's Aspire submission.

The provided challenge excerpt describes capabilities but does not settle that service-minimum question. This is an outstanding organizer clarification, not permission to assume there is no Tencent requirement. Record the actual organizer response or full rule URL here before final deployment: **pending**. No organizer was contacted on the user's behalf.

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
