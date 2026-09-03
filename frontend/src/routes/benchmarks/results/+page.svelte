<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	type Summary = {
		model_id: string;
		model_digest: string | null;
		succeeded: number;
		failed: number;
		average_score: number | null;
		average_confidence: number | null;
		average_latency_ms: number | null;
		council_findings: number;
	};
	type Run = { id: number; status: string; model_ids: string[]; receipt_ids: number[] };
	type Status = {
		run: Run;
		queued: number;
		running: number;
		retrying: number;
		waiting_for_model: number;
		terminal: number;
		summaries: Summary[];
	};
	let runs = $state<Run[]>([]),
		selectedId = $state<number | null>(null),
		result = $state<Status | null>(null),
		error = $state('');
	const fmt = (value: number | null, digits = 2) => (value === null ? '—' : value.toFixed(digits));
	async function refresh() {
		try {
			const response = await fetch('/api/v1/benchmarks');
			if (!response.ok) throw new Error('Unable to load benchmark runs.');
			runs = (await response.json()) as Run[];
			if (!selectedId || !runs.some((run) => run.id === selectedId))
				selectedId = runs[0]?.id ?? null;
			if (selectedId) {
				const status = await fetch(`/api/v1/benchmarks/${selectedId}`);
				if (!status.ok) throw new Error('Unable to load benchmark results.');
				result = (await status.json()) as Status;
			}
			error = '';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Unable to load benchmark results.';
		}
	}
	onMount(() => {
		void refresh();
		const timer = window.setInterval(() => void refresh(), 3000);
		return () => window.clearInterval(timer);
	});
</script>

<svelte:head><title>Benchmarks · Vision Bill</title></svelte:head>
<section class="mx-auto max-w-6xl">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold">Benchmarks</h1>
			<p class="mt-1 text-sm text-on-surface-variant">Live local-model evaluation results.</p>
		</div>
		<a
			class="rounded-lg bg-error px-4 py-2.5 text-sm font-medium text-on-error"
			href={resolve('/benchmarks')}>Create benchmark</a
		>
	</div>
	{#if error}<p class="mt-4 text-sm text-error" role="alert">{error}</p>{/if}
	{#if runs.length === 0}<div
			class="mt-6 rounded-xl border border-dashed border-outline-variant p-8 text-center text-sm text-on-surface-variant"
		>
			No benchmark runs yet.
		</div>{:else}
		<label class="mt-6 block max-w-md text-sm font-medium"
			>Benchmark run<select
				class="mt-1 block w-full rounded-lg border border-outline-variant bg-surface p-2"
				value={selectedId ?? ''}
				onchange={(event) => {
					selectedId = Number(event.currentTarget.value);
					void refresh();
				}}
				>{#each runs as run (run.id)}<option value={run.id}>#{run.id} — {run.status}</option
					>{/each}</select
			></label
		>
		{#if result}<div class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
				<div class="rounded-xl bg-surface-container p-4">
					<p class="text-xs text-on-surface-variant">Completed</p>
					<p class="text-xl font-semibold">
						{result.terminal} / {result.run.receipt_ids.length * result.run.model_ids.length}
					</p>
				</div>
				<div class="rounded-xl bg-surface-container p-4">
					<p class="text-xs text-on-surface-variant">Queued</p>
					<p class="text-xl font-semibold">{result.queued}</p>
				</div>
				<div class="rounded-xl bg-surface-container p-4">
					<p class="text-xs text-on-surface-variant">Running</p>
					<p class="text-xl font-semibold">{result.running}</p>
				</div>
				<div class="rounded-xl bg-surface-container p-4">
					<p class="text-xs text-on-surface-variant">Retrying</p>
					<p class="text-xl font-semibold">{result.retrying}</p>
				</div>
				<div class="rounded-xl bg-surface-container p-4">
					<p class="text-xs text-on-surface-variant">Waiting</p>
					<p class="text-xl font-semibold">{result.waiting_for_model}</p>
				</div>
			</div>
			<div class="mt-6 overflow-x-auto rounded-xl border border-outline-variant">
				<table class="w-full text-left text-sm">
					<thead class="bg-surface-container text-xs text-on-surface-variant"
						><tr
							><th class="p-3">Model</th><th class="p-3">Correctness</th><th class="p-3"
								>Confidence</th
							><th class="p-3">Latency</th><th class="p-3">Success / failed</th><th class="p-3"
								>Council</th
							></tr
						></thead
					><tbody
						>{#each result.summaries as summary (summary.model_id)}<tr
								class="border-t border-outline-variant"
								><td class="p-3 font-medium"
									>{summary.model_id}<br /><span class="text-xs text-on-surface-variant"
										>{summary.model_digest ?? '—'}</span
									></td
								><td class="p-3"
									>{fmt(summary.average_score === null ? null : summary.average_score * 100)}%</td
								><td class="p-3">{fmt(summary.average_confidence)}%</td><td class="p-3"
									>{fmt(summary.average_latency_ms, 0)} ms</td
								><td class="p-3">{summary.succeeded} / {summary.failed}</td><td class="p-3"
									>{summary.council_findings} findings</td
								></tr
							>{/each}</tbody
					>
				</table>
			</div>{/if}
	{/if}
</section>
