# Benchmark local models for NOVA

NOVA uses an OpenAI-compatible chat-completions API. This benchmark script measures candidate models exposed by your local inference runtime without changing NOVA's configuration or saving prompts to NOVA memory.

## Run the benchmark

This is a developer diagnostic; ordinary installed-app usage does not require it.

1. Start your local model runtime.
2. Load the model you want to test and confirm its OpenAI-compatible API is available.
3. Open PowerShell in a NOVA source checkout with the development environment activated.
4. Run:

```powershell
python scripts/benchmark_local_models.py
```

The script's default base URL is `http://127.0.0.1:1235/v1`. It discovers model IDs from `/models`, performs an unmeasured warm-up, and measures short and detailed prompts over repeated runs. It reports median time-to-first-token (TTFT), total response time, and output character count. It does not print generated response text, write to NOVA memory, or change `.env`.

Use a different endpoint:

```powershell
python scripts/benchmark_local_models.py --base-url http://127.0.0.1:1234/v1
```

Test a specific model ID:

```powershell
python scripts/benchmark_local_models.py --model your-model-id
```

For a longer run:

```powershell
python scripts/benchmark_local_models.py --runs 5 --max-tokens 384
```

## Compare candidates carefully

Model size alone does not determine speed or quality. Runtime implementation, quantization, context length, prompt processing, CPU/GPU offload, and model residency all affect results. Compare candidates with identical prompts and benchmark settings. Check answer quality as well as latency before changing your configured model.

## CPU and runtime tuning

NOVA's generic OpenAI-compatible adapter cannot set every inference-runtime option through a universal API. CPU thread count, memory mapping, GPU offload, quantization, and model residency are generally configured in the model runtime itself.

## Interpreting results

- **High TTFT:** investigate model loading, prompt processing, context length, and runtime startup.
- **Low TTFT but high total time:** generation throughput or unnecessarily long output may be the bottleneck.
- Compare medians rather than one run; the first run can be slower due to warm-up.
- Character count is not token count. Some compatible runtimes do not include completion-token usage in streaming responses.

The benchmark targets your configured local endpoint. It does not require a paid API or cloud service.
