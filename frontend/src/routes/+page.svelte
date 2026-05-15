<script lang="ts">
	import { onMount } from 'svelte';

	interface StatusCounts {
		discovered: number;
		stable: number;
		fingerprinted: number;
		extracted: number;
		reconciled: number;
		tagged: number;
		queued_for_review: number;
		transferred: number;
		failed: number;
	}

	let status: StatusCounts | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);

	async function fetchStatus() {
		try {
			const res = await fetch('/api/status');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			status = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fetch status';
		} finally {
			loading = false;
		}
	}

	onMount(fetchStatus);
</script>

<div class="p-6">
	<div class="mb-6">
		<h2 class="text-2xl font-semibold text-text-primary">Pipeline Status</h2>
		<p class="text-sm text-text-secondary mt-1">Overview of your music library processing pipeline</p>
	</div>

	{#if loading}
		<p class="text-text-secondary">Loading...</p>
	{:else if error}
		<p class="text-error">Error: {error}</p>
	{:else if status}
		<div class="grid grid-cols-3 gap-4">
			{#each [
				{ key: 'discovered', label: 'Discovered', icon: '📁' },
				{ key: 'stable', label: 'Stable', icon: '✓' },
				{ key: 'fingerprinted', label: 'Fingerprinted', icon: '🔍' },
				{ key: 'extracted', label: 'Extracted', icon: '📝' },
				{ key: 'reconciled', label: 'Reconciled', icon: '🤖' },
				{ key: 'tagged', label: 'Tagged', icon: '✅' },
				{ key: 'queued_for_review', label: 'Review Queue', icon: '👀' },
				{ key: 'transferred', label: 'Transferred', icon: '🚀' },
				{ key: 'failed', label: 'Failed', icon: '❌' },
			] as item}
				{@const count = status[item.key as keyof StatusCounts] ?? 0}
				<div class="card-border-left {item.key === 'queued_for_review' ? 'card-border-left-warning' : item.key === 'failed' ? 'card-border-left-error' : item.key === 'tagged' || item.key === 'transferred' ? 'card-border-left-success' : ''}">
					<p class="text-xs text-text-muted uppercase tracking-wider">{item.icon} {item.label}</p>
					<p class="text-2xl font-bold text-text-primary mono mt-1">{count}</p>
				</div>
			{/each}
		</div>

		<div class="mt-8">
			<h3 class="text-lg font-medium text-text-primary mb-3">Actions</h3>
			<div class="flex gap-3">
				<button
					class="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors"
					onclick={() => fetch('/api/pipeline/start', { method: 'POST' }).then(() => fetchStatus())}
				>
					▶ Start Pipeline
				</button>
				<button
					class="px-4 py-2 bg-surface-700 hover:bg-surface-600 text-text-primary rounded-md text-sm font-medium border border-border transition-colors"
				>
					↻ Refresh
				</button>
			</div>
		</div>
	{/if}
</div>