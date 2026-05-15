<script lang="ts">
	import { onMount } from 'svelte';

	interface ReviewItem {
		file_path: string;
		state: string;
		confidence: number;
		error: string | null;
	}

	let items: ReviewItem[] = $state([]);
	let loading = $state(true);

	async function fetchReview() {
		try {
			const res = await fetch('/api/review');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			items = await res.json();
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	async function approve(item: ReviewItem) {
		// TODO: Open tag editor, submit approved tags
		console.log('Approve:', item.file_path);
	}

	async function reject(item: ReviewItem) {
		await fetch(`/api/review/${encodeURIComponent(item.file_path)}/reject`, { method: 'POST' });
		await fetchReview();
	}

	onMount(fetchReview);
</script>

<div class="p-6">
	<div class="mb-6">
		<h2 class="text-2xl font-semibold text-text-primary">Review Queue</h2>
		<p class="text-sm text-text-secondary mt-1">Files that need your approval before tags are written</p>
	</div>

	{#if loading}
		<p class="text-text-secondary">Loading...</p>
	{:else if items.length === 0}
		<div class="card-border-left card-border-left-success">
			<p class="text-text-primary">✅ No items in review queue</p>
			<p class="text-text-muted text-sm mt-1">All files have been auto-tagged or are still processing</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each items as item}
				<div class="card-border-left card-border-left-warning">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-text-primary font-medium">{item.file_path.split('/').pop()}</p>
							<p class="text-xs text-text-muted mono mt-0.5">{item.file_path}</p>
						</div>
						<div class="flex items-center gap-2">
							<span class="badge badge-confidence">{(item.confidence * 100).toFixed(0)}%</span>
							<button
								class="px-3 py-1 text-xs bg-success/20 text-success rounded hover:bg-success/30 transition-colors"
								onclick={() => approve(item)}
							>
								Approve
							</button>
							<button
								class="px-3 py-1 text-xs bg-error/20 text-error rounded hover:bg-error/30 transition-colors"
								onclick={() => reject(item)}
							>
								Reject
							</button>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>