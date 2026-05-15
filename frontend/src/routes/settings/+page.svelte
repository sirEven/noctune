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
		container_path: string | null;
		exists: boolean;
		source: string;
		label: string;
		navidrome_uses: boolean;
		mount_type: string | null;
		device: string | null;
		mount_point: string | null;
		fstype: string | null;
		size: string | null;
		used_pct: string | null;
		on_root: boolean;
	}

	interface MountInfo {
		device: string;
		mount_point: string;
		fstype: string;
		size: string;
		used_pct: string;
		on_root: boolean;
	}

	interface NavidromeTest {
		reachable: boolean;
		auth_ok: boolean;
		version: string;
		error: string;
	}

	interface SshTest {
		ok: boolean;
		message: string;
	}

	interface RemoteConfig {
		host: string;
		port: number;
		user: string;
		password: string;
	}

	interface NavidromeConfig {
		url: string;
		username: string;
		password: string;
		music_folder: string;
	}

	interface Config {
		source_dir: string;
		dest_dir: string;
		remote: RemoteConfig;
		navidrome: NavidromeConfig | null;
	}

	let config = $state<Config | null>(null);
	let localPaths = $state<{ source: PathCandidate[]; dest: PathCandidate[] } | null>(null);
	let remotePaths = $state<{ music_folder: MusicCandidate[]; mounts: MountInfo[]; navidrome_type?: string; error?: string } | null>(null);
	let navidromeTest = $state<NavidromeTest | null>(null);
	let sshTest = $state<SshTest | null>(null);
	let saving = $state(false);
	let probingLocal = $state(false);
	let probingRemote = $state(false);
	let testingSsh = $state(false);
	let testingNavidrome = $state(false);
	let message: string | null = $state(null);
	let error: string | null = $state(null);

	// Edit form state
	let sourceDir = $state('');
	let destDir = $state('');
	let remoteHost = $state('');
	let remotePort = $state(22);
	let remoteUser = $state('');
	let remotePassword = $state('');
	let navidromeUrl = $state('');
	let navidromeUsername = $state('');
	let navidromePassword = $state('');
	let navidromeMusicFolder = $state('');

	async function loadConfig() {
		try {
			const res = await fetch('/api/config');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			config = data;
			sourceDir = data.source_dir ?? '';
			destDir = data.dest_dir ?? '';
			if (data.remote) {
				remoteHost = data.remote.host ?? '';
				remotePort = data.remote.port ?? 22;
				remoteUser = data.remote.user ?? '';
				remotePassword = ''; // never pre-fill passwords
			}
			if (data.navidrome) {
				navidromeUrl = data.navidrome.url ?? '';
				navidromeUsername = data.navidrome.username ?? '';
				navidromePassword = '';
				navidromeMusicFolder = data.navidrome.music_folder ?? '';
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
			if (remoteHost) body.remote_host = remoteHost;
			if (remotePort) body.remote_port = remotePort;
			if (remoteUser) body.remote_user = remoteUser;
			if (remotePassword) body.remote_password = remotePassword;
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
		remotePaths = null;
		try {
			await saveConfig();
			const res = await fetch('/api/settings/paths/remote');
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const data = await res.json();
			remotePaths = data;
			if (data.error) {
				error = data.error;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to probe remote paths';
		} finally {
			probingRemote = false;
		}
	}

	async function testSsh() {
		testingSsh = true;
		error = null;
		sshTest = null;
		try {
			await saveConfig();
			const res = await fetch('/api/settings/ssh/test');
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			sshTest = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to test SSH';
		} finally {
			testingSsh = false;
		}
	}

	async function testNavidrome() {
		testingNavidrome = true;
		error = null;
		navidromeTest = null;
		try {
			await saveConfig();
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
	<!-- Sticky header -->
	<div class="sticky top-0 z-10 -mx-6 -mt-6 px-6 py-4 bg-surface-900/95 backdrop-blur border-b border-border flex items-center justify-between mb-6">
		<div>
			<h2 class="text-2xl font-semibold text-text-primary">Settings</h2>
			<p class="text-xs text-text-muted">Configure Noctune</p>
		</div>
		<button
			class="px-6 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50 shrink-0"
			onclick={saveConfig}
			disabled={saving}
		>
			{saving ? 'Saving...' : 'Save Settings'}
		</button>
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

	<!-- Section 1: Source Directory (local) -->
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

	<!-- Section 2: Remote Machine -->
	<div class="card-border-left mb-6">
		<h3 class="text-lg font-medium text-text-primary mb-3">Remote Machine</h3>
		<p class="text-xs text-text-muted mb-4">SSH connection to the machine running Navidrome — used for file transfer, path probing, and deletion</p>

		<div class="space-y-4">
			<div class="grid grid-cols-3 gap-4">
				<div>
					<label for="remote-host" class="block text-sm font-medium text-text-secondary mb-1">Host</label>
					<input
						id="remote-host"
						type="text"
						bind:value={remoteHost}
						placeholder="192.168.178.107"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="remote-port" class="block text-sm font-medium text-text-secondary mb-1">Port</label>
					<input
						id="remote-port"
						type="number"
						bind:value={remotePort}
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="remote-user" class="block text-sm font-medium text-text-secondary mb-1">User</label>
					<input
						id="remote-user"
						type="text"
						bind:value={remoteUser}
						placeholder="eversin"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
			</div>

			<div>
				<label for="remote-password" class="block text-sm font-medium text-text-secondary mb-1">Password</label>
				<p class="text-xs text-text-muted mb-1">Leave empty if using key-based auth (recommended)</p>
				<input
					id="remote-password"
					type="password"
					bind:value={remotePassword}
					placeholder="••••••••"
					class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
				/>
			</div>

			<div>
				<label for="dest-dir" class="block text-sm font-medium text-text-secondary mb-1">Destination Directory</label>
				<p class="text-xs text-text-muted mb-1">Path on the remote machine where processed music lands</p>
				<input
					id="dest-dir"
					type="text"
					bind:value={destDir}
					placeholder="/data/music"
					class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
				/>
			</div>

			<!-- SSH test result -->
			{#if sshTest}
				<div class="p-3 rounded-md {sshTest.ok ? 'bg-success/10 border border-success/30 text-success' : 'bg-error/10 border border-error/30 text-error'}">
					{sshTest.ok ? '✓' : '✗'} {sshTest.message}
				</div>
			{/if}

			<div>
				<button
					class="px-4 py-2 bg-surface-700 hover:bg-surface-600 border border-border text-text-secondary rounded-md text-sm transition-colors disabled:opacity-50"
					onclick={testSsh}
					disabled={testingSsh}
				>
					{testingSsh ? 'Testing...' : 'Test SSH'}
				</button>
			</div>
		</div>
	</div>

	<!-- Section 3: Navidrome -->
	<div class="card-border-left mb-6">
		<h3 class="text-lg font-medium text-text-primary mb-3">Navidrome</h3>
		<p class="text-xs text-text-muted mb-4">The music server API — for browsing your library and triggering rescans</p>

		<div class="space-y-4">
			<div>
				<label for="navidrome-url" class="block text-sm font-medium text-text-secondary mb-1">URL</label>
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
					<label for="nav-username" class="block text-sm font-medium text-text-secondary mb-1">Username</label>
					<input
						id="nav-username"
						type="text"
						bind:value={navidromeUsername}
						placeholder="admin"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
				<div>
					<label for="nav-password" class="block text-sm font-medium text-text-secondary mb-1">Password</label>
					<input
						id="nav-password"
						type="password"
						bind:value={navidromePassword}
						placeholder="••••••••"
						class="w-full px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
				</div>
			</div>

			<div>
				<label for="music-folder" class="block text-sm font-medium text-text-secondary mb-1">Music Folder</label>
				<p class="text-xs text-text-muted mb-1">Where Navidrome looks for music on the remote machine. Usually the same as Destination Directory.</p>
				<div class="flex gap-2">
					<input
						id="music-folder"
						type="text"
						bind:value={navidromeMusicFolder}
						placeholder="/data/music"
						class="flex-1 px-3 py-2 bg-surface-700 border border-border rounded-md text-text-primary text-sm focus:outline-none focus:border-primary transition-colors"
					/>
					<button
						class="px-3 py-2 bg-surface-700 hover:bg-surface-600 border border-border text-text-secondary rounded-md text-xs transition-colors disabled:opacity-50 shrink-0"
						onclick={probeRemote}
						disabled={probingRemote}
					>
						{probingRemote ? '...' : '🔍 Probe'}
					</button>
				</div>
			</div>

			<!-- Remote path suggestions (from probing) -->
			{#if remotePaths}
				{#if remotePaths.error}
					<div class="p-3 bg-error/10 border border-error/30 rounded-md text-error text-xs">
						{remotePaths.error}
					</div>
				{:else if remotePaths.music_folder?.length > 0}
					<div>
						{#if remotePaths.navidrome_type === 'docker'}
							<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Navidrome runs in Docker — host paths shown</p>
						{:else if remotePaths.navidrome_type === 'bare_metal'}
							<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Navidrome runs bare-metal on this machine</p>
						{:else}
							<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Found on remote</p>
						{/if}
						<div class="space-y-2">
							{#each remotePaths.music_folder as candidate}
								<button
									class="w-full text-left px-3 py-2.5 rounded text-xs transition-colors {candidate.navidrome_uses ? 'bg-primary/15 border border-primary/40 text-text-primary' : candidate.exists ? 'bg-surface-700 hover:bg-surface-600 text-text-primary' : 'bg-surface-800 text-text-muted'}  {!candidate.exists && !candidate.navidrome_uses ? 'opacity-60' : ''}"
									onclick={() => {
										if (candidate.exists || candidate.navidrome_uses) {
											navidromeMusicFolder = candidate.path;
											destDir = candidate.path;
										}
									}}
									disabled={!candidate.exists && !candidate.navidrome_uses}
								>
									<!-- Top line: badge + path + container mapping -->
									<div class="flex items-center gap-2 flex-wrap">
										{#if candidate.navidrome_uses}
											<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-600 text-white leading-none shrink-0">NAVIDROME</span>
										{/if}
										<span class="font-medium font-mono">{candidate.path}</span>
										{#if !candidate.exists}
											<span class="text-text-muted">✗ not found</span>
										{/if}
										{#if candidate.container_path && candidate.container_path !== candidate.path}
											<span class="text-text-muted">← {candidate.container_path} in container</span>
										{/if}
									</div>
									<!-- Second line: source label -->
									<div class="text-text-muted mt-0.5">{candidate.label}</div>
									<!-- Third line: device context chips -->
									{#if candidate.device || candidate.fstype || candidate.size}
										<div class="flex items-center gap-1.5 flex-wrap mt-1">
											{#if candidate.mount_type === 'bind'}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">bind mount</span>
											{:else if candidate.mount_type === 'volume'}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">Docker volume</span>
											{/if}
											{#if candidate.device}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">{candidate.device}</span>
											{/if}
											{#if candidate.fstype}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">{candidate.fstype}</span>
											{/if}
											{#if candidate.size}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">{candidate.size}</span>
											{/if}
											{#if candidate.used_pct}
												<span class="px-1.5 py-0.5 rounded bg-surface-600/60 text-text-muted text-[10px]">{candidate.used_pct}% used</span>
											{/if}
											{#if candidate.on_root}
												<span class="px-1.5 py-0.5 rounded bg-amber-600/20 text-amber-400 text-[10px] border border-amber-600/30">OS disk</span>
											{/if}
										</div>
									{/if}
								</button>
							{/each}
						</div>
					</div>
				{:else if !remotePaths.error}
					<p class="text-xs text-text-muted">No music paths found on remote</p>
				{/if}
			{/if}

			<!-- Available storage mounts on remote -->
			{#if remotePaths?.mounts && remotePaths.mounts.length > 0}
				<div>
					<p class="text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">Available storage on remote</p>
					<div class="space-y-1">
						{#each remotePaths.mounts as mount}
							<div class="flex items-center gap-2 px-3 py-1.5 rounded text-xs bg-surface-700/50">
								<span class="font-mono text-text-secondary">{mount.device}</span>
								<span class="text-text-muted">→</span>
								<span class="font-mono text-text-primary">{mount.mount_point}</span>
								<span class="text-text-muted">{mount.fstype}</span>
								<span class="text-text-muted">{mount.size}</span>
								<span class="text-text-muted">{mount.used_pct}% used</span>
								{#if mount.on_root}
									<span class="px-1.5 py-0.5 rounded bg-amber-600/20 text-amber-400 text-[10px] border border-amber-600/30">OS disk</span>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Navidrome test result -->
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

			<div>
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
</div>