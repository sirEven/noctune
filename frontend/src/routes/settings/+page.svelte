<script lang="ts">
	import { onMount } from 'svelte';

	interface PathCandidate {
		path: string;
		expanded: string;
		exists: boolean;
		is_dir: boolean;
	}

	interface MusicCandidate {
		path: string;
		exists: boolean;
		source: string;
	}

	interface NavidromeTest {
		reachable: boolean;
		auth_ok: boolean;
		version: string;
		error: string;
	}

	interface Config {
		source_dir: string;
		dest_host: string;
		dest_user: string;
		dest_dir: string;
		navidrome: {
			url: string;
			username: string;
			password: string;
			music_folder: string;
			ssh_host: string;
			ssh_user: string;
			ssh_port: number;
		} | null;
	}

	let config = $state<Config | null>(null);
	let localPaths = $state<{ source: PathCandidate[]; dest: PathCandidate[] } | null>(null);
	let remotePaths = $state<{ music_folder: MusicCandidate[] } | null>(null);
	let navidromeTest = $state<NavidromeTest | null>(null);
	let loading = $state(false);
	let saving = $state(false);
	let probingLocal = $state(false);
	let probingRemote = $state(false);
	let testingNavidrome = $state(false);
	let message: string | null = $state(null);
	let error: string | null = $state(null);

	// Edit form state
	let sourceDir = $state('');
	let destDir = $state('');
	let destHost = $state('');
	let destUser = $state('');
	let navidromeUrl = $state('');
	let navidromeUsername = $state('');
	let navidromePassword = $state('');
	let navidromeMusicFolder = $state('');
	let navidromeSshHost = $state('');
	let navidromeSshUser = $state('');
	let navidromeSshPort = $state(22);

	async function loadConfig() {
		try {
			const res = await fetch('/api/config');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			config = data;
			sourceDir = data.source_dir ?? '';
			destDir = data.dest_dir ?? '';
			destHost = data.dest_host ?? '';
			destUser = data.dest_user ?? '';
			if (data.navidrome) {
				navidromeUrl = data.navidrome.url ?? '';
				navidromeUsername = data.navidrome.username ?? '';
				navidromePassword = ''; // don't pre-fill password
				navidromeMusicFolder = data.navidrome.music_folder ?? '';
				navidromeSshHost = data.navidrome.ssh_host ?? '';
				navidromeSshUser = data.navidrome.ssh_user ?? '';
				navidromeSshPort = data.navidrome.ssh_port ?? 22;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load config';
		}
	}

	async function saveConfig() {
		saving = true;
		message = null;
		error = null;
		try {
			const body: Record<string, string | number> = {};
			if (sourceDir) body.source_dir = sourceDir;
			if (destDir) body.dest_dir = destDir;
			if (destHost) body.dest_host = destHost;
			if (destUser) body.dest_user = destUser;
			if (navidromeUrl) body.navidrome_url = navidromeUrl;
			if (navidromeUsername) body.navidrome_username = navidromeUsername;
			if (navidromePassword) body.navidrome_password = navidromePassword;
			if (navidromeMusicFolder) body.navidrome_music_folder = navidromeMusicFolder;

			const res = await fetch('/api/config', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			message = 'Settings saved';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			saving = false;
		}
	}

	async function probeLocal() {
		probingLocal = true;
		error = null;
		try {
			const res = await fetch('/api/settings/paths/local');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			localPaths = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to probe local paths';
		} finally {
			probingLocal = false;
		}
	}

	async function probeRemote() {
		probingRemote = true;
		error = null;
		try {
			const res = await fetch('/api/settings/paths/remote');
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			remotePaths = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to probe remote paths';
		} finally {
			probingRemote = false;
		}
	}

	async function testNavidrome() {
		testingNavidrome = true;
		error = null;
		try {
			// Save first if changed
			if (navidromeUrl || navidromeUsername || navidromePassword) {
				await saveConfig();
			}
			const res = await fetch('/api/settings/navidrome/test');
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			navidromeTest = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to test Navidrome';
		} finally {
			testingNavidrome = false;
		}
	}

	onMount(() => {
		loadConfig();
	});
</script>

<div class="p-6 max-w-2xl">
	<div class="mb-6">
		<h2 class="text-2xl font-semibold text-text-primary">Settings</h2>
		<p class="text-sm text-text-secondary mt-1">Configure Noctune directories and Navidrome connection</p>
	</div>

	{#if message}
		<div class="mb-4 p-3 bg-success/10 border border-success/30 rounded-md text-success text-sm">
			{message}
		</div>
	{/if}

	{#if error}
		<div class="mb-4 p-3 bg-error/10 border border-error/30 rounded-md text-error text-sm">
			{error}
		</div>
	{/if}

	<!-- Source Directory (local) -->
	<div class="card-border-left mb-6">
		<h3 class="text-lg font-medium text-text-primary mb-3">Source Directory (local)</h3>
		<p class="text-xs text-text-muted mb-4">The folder on <strong>this machine</strong> that Noctune watches for new music files</p>

		<div class="space-y-3">
			<div>
				<div class="flex gap-2">
					<input
						id="source-dir"
						type="text"
						bind:value={sourceDir}
						placeholder="~/Music/Incoming"
						class="flex-1 px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
					<button
						class="px-3 py-2 bg-surface-700 hover:bg-surface-600 border border-border text-text-secondary rounded-md text-xs transition-colors"
						onclick={probeLocal}
						disabled={probingLocal}
					>
						{probingLocal ? '...' : '🔍 Suggest'}
					</button>
				</div>
			</div>

			<!-- Local path suggestions — right under the field they're for -->
			{#if localPaths}
				<div>
					<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Found on this machine</p>
					<div class="space-y-1">
						{#each localPaths.source as candidate}
							<button
								class="w-full text-left px-3 py-1.5 rounded text-xs transition-colors {candidate.exists ? 'bg-surface-700 hover:bg-surface-600 text-text-primary' : 'bg-surface-800 text-text-muted'}"
								onclick={() => { if (candidate.exists) sourceDir = candidate.path; }}
								disabled={!candidate.exists}
							>
								{candidate.path} {candidate.exists ? '✓' : '✗'}
							</button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</div>

	<!-- Remote / Navidrome Connection -->
	<div class="card-border-left mb-6">
		<h3 class="text-lg font-medium text-text-primary mb-3">Navidrome Connection</h3>
		<p class="text-xs text-text-muted mb-4">How Noctune connects to Navidrome on the remote machine</p>

		<div class="space-y-4">
			<!-- Remote Host & User -->
			<div class="grid grid-cols-2 gap-4">
				<div>
					<label for="remote-host" class="block text-sm font-medium text-text-secondary mb-1">Remote Host</label>
					<p class="text-xs text-text-muted mb-1">Hostname or IP of the remote machine</p>
					<input
						id="remote-host"
						type="text"
						bind:value={destHost}
						placeholder="192.168.178.107"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="remote-user" class="block text-sm font-medium text-text-secondary mb-1">Remote User</label>
					<p class="text-xs text-text-muted mb-1">SSH username on the remote machine</p>
					<input
						id="remote-user"
						type="text"
						bind:value={destUser}
						placeholder="eversin"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
			</div>

			<!-- Navidrome API -->
			<div>
				<label for="navidrome-url" class="block text-sm font-medium text-text-secondary mb-1">Navidrome URL</label>
				<input
					id="navidrome-url"
					type="text"
					bind:value={navidromeUrl}
					placeholder="http://192.168.178.107:4533"
					class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
				/>
			</div>

			<div class="grid grid-cols-2 gap-4">
				<div>
					<label for="nav-username" class="block text-sm font-medium text-text-secondary mb-1">Navidrome Username</label>
					<input
						id="nav-username"
						type="text"
						bind:value={navidromeUsername}
						placeholder="admin"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="nav-password" class="block text-sm font-medium text-text-secondary mb-1">Navidrome Password</label>
					<input
						id="nav-password"
						type="password"
						bind:value={navidromePassword}
						placeholder="••••••••"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
			</div>

			<!-- Destination Directory (on remote) -->
			<div>
				<label for="dest-dir" class="block text-sm font-medium text-text-secondary mb-1">Destination Directory (on remote)</label>
				<p class="text-xs text-text-muted mb-2">Path on the remote machine where processed music lands</p>
				<input
					id="dest-dir"
					type="text"
					bind:value={destDir}
					placeholder="/data/music"
					class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
				/>
			</div>

			<!-- Music Folder (for Navidrome API browsing) -->
			<div>
				<label for="music-folder" class="block text-sm font-medium text-text-secondary mb-1">Music Folder (Navidrome)</label>
				<p class="text-xs text-text-muted mb-2">Navidrome's MusicFolder — where it indexes from</p>
				<div class="flex gap-2">
					<input
						id="music-folder"
						type="text"
						bind:value={navidromeMusicFolder}
						placeholder="/data/music"
						class="flex-1 px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
					<button
						class="px-3 py-2 bg-surface-700 hover:bg-surface-600 border border-border text-text-secondary rounded-md text-xs transition-colors"
						onclick={probeRemote}
						disabled={probingRemote}
					>
						{probingRemote ? '...' : '🔍 Probe Remote'}
					</button>
				</div>
			</div>

			<!-- Remote path suggestions -->
			{#if remotePaths}
				<div>
					<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Found on remote</p>
					<div class="space-y-1">
						{#each remotePaths.music_folder as candidate}
							<button
								class="w-full text-left px-3 py-1.5 rounded text-xs transition-colors {candidate.exists ? 'bg-surface-700 hover:bg-surface-600 text-text-primary' : 'bg-surface-800 text-text-muted'}"
								onclick={() => { if (candidate.exists) navidromeMusicFolder = candidate.path; }}
								disabled={!candidate.exists}
							>
								{candidate.path} {candidate.exists ? '✓' : '✗'}
								<span class="text-text-muted">({candidate.source})</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<div class="grid grid-cols-2 gap-4">
				<div>
					<label for="ssh-host" class="block text-sm font-medium text-text-secondary mb-1">SSH Host</label>
					<input
						id="ssh-host"
						type="text"
						bind:value={navidromeSshHost}
						placeholder="192.168.178.107"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="ssh-port" class="block text-sm font-medium text-text-secondary mb-1">SSH Port</label>
					<input
						id="ssh-port"
						type="number"
						bind:value={navidromeSshPort}
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
			</div>

			<!-- Connection test result -->
			{#if navidromeTest}
				<div class="p-3 rounded-md {navidromeTest.auth_ok ? 'bg-success/10 border border-success/30 text-success' : 'bg-error/10 border border-error/30 text-error'}">
					{#if navidromeTest.reachable && navidromeTest.auth_ok}
						✓ Connected to Navidrome v{navidromeTest.version}
					{:else if navidromeTest.reachable}
						✗ Reachable but auth failed: {navidromeTest.error}
					{:else}
						✗ Cannot reach Navidrome: {navidromeTest.error}
					{/if}
				</div>
			{/if}

			<div class="flex gap-3">
				<button
					class="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
					onclick={testNavidrome}
					disabled={testingNavidrome}
				>
					{testingNavidrome ? 'Testing...' : 'Test Connection'}
				</button>
			</div>
		</div>
	</div>

	<!-- Save -->
	<div class="flex items-center gap-3">
		<button
			class="px-6 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
			onclick={saveConfig}
			disabled={saving}
		>
			{saving ? 'Saving...' : 'Save Settings'}
		</button>
	</div>
</div>