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

	type DaemonState = 'stopped' | 'running' | 'paused';

	let status: StatusCounts | null = $state(null);
	let loading = $state(true);
	let error: string | null = $state(null);
	let daemonState: DaemonState | null = $state(null);
	let daemonLoading = $state(false);

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

	async function fetchDaemonStatus() {
		try {
			const res = await fetch('/api/daemon/status');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			daemonState = data.state;
		} catch {
			// Daemon might not be initialized yet
		}
	}

	async function toggleDaemon() {
		daemonLoading = true;
		try {
			let endpoint: string;
			if (daemonState === 'stopped') {
				endpoint = '/api/daemon/start';
			} else if (daemonState === 'paused') {
				endpoint = '/api/daemon/resume';
			} else {
				endpoint = '/api/daemon/pause';
			}
			const res = await fetch(endpoint, { method: 'POST' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			daemonState = data.status as DaemonState;
		} catch (e) {
			console.error('Daemon toggle failed:', e);
		} finally {
			daemonLoading = false;
		}
	}

	async function stopDaemon() {
		daemonLoading = true;
		try {
			const res = await fetch('/api/daemon/stop', { method: 'POST' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			daemonState = data.status as DaemonState;
		} catch (e) {
			console.error('Daemon stop failed:', e);
		} finally {
			daemonLoading = false;
		}
	}

	onMount(() => {
		fetchStatus();
		fetchDaemonStatus();
	});
</script>

<div class="p-6">
	<div class="mb-6">
		<h2 class="text-2xl font-semibold text-text-primary">Pipeline Status</h2>
		<p class="text-sm text-text-secondary mt-1">Overview of your music library processing pipeline</p>
	</div>

	<!-- Daemon Control -->
	<div class="card-border-left mb-6" class:card-border-left-success={daemonState === 'running'} class:card-border-left-warning={daemonState === 'paused'}>
		<div class="flex items-center justify-between">
			<div>
				<p class="text-xs text-text-muted uppercase tracking-wider">Daemon</p>
				<p class="text-lg font-semibold text-text-primary mt-0.5">
					{#if daemonState === 'running'}
						🟢 Running
					{:else if daemonState === 'paused'}
						🟡 Paused
					{:else}
						🔴 Stopped
					{/if}
				</p>
			</div>
			<div class="flex gap-2">
				<button
					class="px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 {daemonState === 'stopped' ? 'bg-primary text-white hover:bg-primary-hover' : daemonState === 'running' ? 'bg-warning text-surface-900 hover:bg-yellow-600' : 'bg-success text-white hover:bg-emerald-600'}"
					onclick={toggleDaemon}
					disabled={daemonLoading}
				>
					{#if daemonState === 'running'}
						⏸ Pause
					{:else if daemonState === 'paused'}
						▶ Resume
					{:else}
						▶ Start
					{/if}
				</button>
				{#if daemonState !== 'stopped'}
					<button
						class="px-3 py-2 bg-surface-700 hover:bg-surface-600 text-error rounded-md text-sm font-medium transition-colors disabled:opacity-50"
						onclick={stopDaemon}
						disabled={daemonLoading}
					>
						⏹ Stop
					</button>
				{/if}
			</div>
		</div>
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
					class="px-4 py-2 bg-surface-700 hover:bg-surface-600 text-text-primary rounded-md text-sm font-medium border border-border transition-colors"
					onclick={() => { fetchStatus(); fetchDaemonStatus(); }}
				>
					↻ Refresh
				</button>
			</div>
		</div>
	{/if}
</div>