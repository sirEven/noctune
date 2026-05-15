<script lang="ts">
	import '../app.css';
	let { children } = $props();
</script>

<div class="flex h-screen bg-surface-900">
	<!-- Sidebar -->
	<aside class="w-56 bg-surface-800 border-r border-border flex flex-col">
		<div class="p-4 border-b border-border">
			<h1 class="text-lg font-semibold text-text-primary tracking-tight">Noctune</h1>
			<p class="text-xs text-text-muted mt-0.5">Music Library Manager</p>
		</div>
		<nav class="flex-1 p-2 space-y-0.5">
			<a href="/" class="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-secondary hover:bg-surface-700 hover:text-text-primary transition-colors">
				<span class="text-base">📊</span> Pipeline Status
			</a>
			<a href="/review" class="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-secondary hover:bg-surface-700 hover:text-text-primary transition-colors">
				<span class="text-base">👀</span> Review Queue
			</a>
			<a href="/duplicates" class="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-secondary hover:bg-surface-700 hover:text-text-primary transition-colors">
				<span class="text-base">🔍</span> Duplicates
			</a>
			<a href="/normalize" class="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-secondary hover:bg-surface-700 hover:text-text-primary transition-colors">
				<span class="text-base">📂</span> Normalize
			</a>
		</nav>
		<div class="p-3 border-t border-border">
			<p class="text-xs text-text-muted">v0.1.0</p>
		</div>
	</aside>

	<!-- Main Content -->
	<main class="flex-1 overflow-auto">
		{@render children()}
	</main>
</div>