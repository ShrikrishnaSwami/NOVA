# Benchmark local models for NOVA

NOVA's response timings show that short replies are fast but longer generation is
the main bottleneck on a low-power CPU. Before changing the default model, measure
candidate models through the same local runtime and the same prompts.

## Run the benchmark

1. Start Bionic and load the model you want to test.
2. Open PowerShell in the NOVA repository and activate the virtual environment.
3. Run:

```powershell
python scripts/benchmark_local_models.py
```

The script uses Bionic's default OpenAI-compatible address,
`http://127.0.0.1:1235/v1`. It discovers model IDs from `/models`, performs one
unmeasured warm-up, and then measures short and detailed prompts three times.
It reports median time-to-first-token (TTFT), total time, and output character
count. It never prints generated response text, writes to NOVA's memory, or
changes your `.env`.

If your runtime uses another address:

```powershell
python scripts/benchmark_local_models.py --base-url http://127.0.0.1:1235/v1
```

To test a specific model ID (or several IDs exposed by the runtime):

```powershell
python scripts/benchmark_local_models.py --model qwen3-1.7b
```

For a longer, more stable run:

```powershell
python scripts/benchmark_local_models.py --runs 5 --max-tokens 384
```

## Candidate models to compare

These are candidates, not guaranteed speed winners. Actual performance depends
on the runtime, quantization, context length, and CPU kernels. Test one model at
a time using the same benchmark settings.

- **Qwen3 0.6B Instruct (GGUF):** first candidate when speed is the priority.
  It is much smaller than the current 1.7B model, but may be less capable on
  detailed explanations and multi-step tasks.
  Model: https://huggingface.co/Qwen/Qwen3-0.6B-GGUF
- **Llama 3.2 1B Instruct:** a compact alternative worth comparing for general
  chat. Confirm that your runtime has a compatible quantized build.
- **SmolLM2 1.7B Instruct:** same broad parameter class as the current model;
  worth testing for instruction-following differences, but do not assume it
  will be faster.

Do not replace your current model just because a candidate has fewer parameters.
Compare both latency and answer quality on the same questions.

## CPU and runtime tuning

NOVA uses a generic OpenAI-compatible HTTP API. Settings such as CPU thread count,
CPU instruction-set kernels, memory mapping, GPU offload, and model residency
belong to the inference runtime and cannot be safely configured by NOVA through
a universal API parameter.

For this laptop (i5-8350U, 16 GB RAM, Intel UHD 620), start with the runtime's
CPU backend and a Q4 quantization. If Bionic exposes CPU thread settings, test
a small range around the physical core count (4) and compare results rather
than assuming more threads are faster. Keep the model loaded between requests
if the runtime offers that option.

## Interpreting results

- High TTFT: investigate model loading, prompt processing, context size, and
  runtime startup.
- Low TTFT but high total time: generation throughput or an unnecessarily long
  answer is the likely bottleneck.
- Compare median values, not one run. The first run can be slower due to warm-up.
- The script's character count is not a token count; runtimes do not consistently
  include completion-token usage in streaming responses.

No paid API or cloud service is used by this benchmark.
