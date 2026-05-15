<script lang="ts">
	import { onMount } from 'svelte';

	interface Song {
		id: string;
		title: string;
		artist?: string;
		album?: string;
		path?: string;
		albumId?: string;
		duration?: number;
		year?: number;
	}

	interface Album {
		id: string;
		name: string;
		artist?: string;
		songCount?: number;
		coverArt?: string;
	}

	let searchQuery = $state('');
	let searchResults = $state<{ songs: Song[]; albums: Album[] }>({ songs: [], albums: [] });
	let albums = $state<Album[]>([]);
	let selectedAlbum = $state<{ id: string; name: string; artist: string; songs: Song[] } | null>(null);
	let loading = $state(false);
	let error: string | null = $state(null);
	let deleting: string | null = $state(null);
	let confirmDelete: string | null = $state(null);

	async function searchLibrary() {
		if (!searchQuery.trim()) return;
		loading = true;
		error = null;
		try {
			const res = await fetch(`/api/library/search?query=${encodeURIComponent(searchQuery)}`);
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const data = await res.json();
			searchResults = {
				songs: data.searchResult3?.song || [],
				albums: data.searchResult3?.album || [],
			};
		} catch (e) {
			error = e instanceof Error ? e.message : 'Search failed';
		} finally {
			loading = false;
		}
	}

	async function loadAlbums(offset = 0) {
		loading = true;
		error = null;
		try {
			const res = await fetch(`/api/library/albums?offset=${offset}&size=50`);
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const data = await res.json();
			albums = data.albumList2?.album || [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load albums';
		} finally {
			loading = false;
		}
	}

	async function openAlbum(albumId: string) {
		loading = true;
		error = null;
		try {
			const res = await fetch(`/api/library/album/${albumId}`);
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const data = await res.json();
			selectedAlbum = {
				id: data.album.id,
				name: data.album.name || data.album.title || 'Unknown Album',
				artist: data.album.artist || 'Unknown Artist',
				songs: (data.album.song || []).map((s: any) => ({
					id: s.id,
					title: s.title || 'Unknown',
					artist: s.artist || s.albumArtist || '',
					album: s.album || '',
					path: s.path || '',
					duration: s.duration,
					year: s.year,
				})),
			};
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load album';
		} finally {
			loading = false;
		}
	}

	async function deleteFile(path: string) {
		deleting = path;
		error = null;
		try {
			const res = await fetch(`/api/library/file?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			// Remove from UI
			if (selectedAlbum) {
				selectedAlbum = { ...selectedAlbum, songs: selectedAlbum.songs.filter(s => s.path !== path) };
			}
			searchResults = {
				...searchResults,
				songs: searchResults.songs.filter(s => s.path !== path),
			};
			confirmDelete = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Delete failed';
		} finally {
			deleting = null;
		}
	}

	async function deleteAlbumDirectory(path: string) {
		deleting = path;
		error = null;
		try {
			const res = await fetch(`/api/library/directory?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			if (selectedAlbum && selectedAlbum.id === confirmDelete) {
				selectedAlbum = null;
			}
			confirmDelete = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Delete failed';
		} finally {
			deleting = null;
		}
	}

	function formatDuration(seconds?: number): string {
		if (!seconds) return '--:--';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		return `${m}:${s.toString().padStart(2, '0')}`;
	}

	onMount(() => {
		loadAlbums();
	});
</script>

<div class="p-6">
	<div class="mb-6">
		<h2 class="text-2xl font-semibold text-text-primary">Library</h2>
		<p class="text-sm text-text-secondary mt-1">Browse and manage your Navidrome music library</p>
	</div>

	{#if error}
		<div class="mb-4 p-3 bg-error/10 border border-error/30 rounded-md text-error text-sm">
			{error}
		</div>
	{/if}

	<!-- Search -->
	<div class="mb-6">
		<div class="flex gap-2">
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Search artists, albums, songs..."
				class="flex-1 px-4 py-2 bg-surface-700 border border-border rounded-md text-text-primary placeholder-text-muted focus:outline-none focus:border-primary transition-colors"
				onkeydown={(e) => e.key === 'Enter' && searchLibrary()}
			/>
			<button
				class="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-md text-sm font-medium transition-colors disabled:opacity-50"
				onclick={searchLibrary}
				disabled={loading}
			>
				Search
			</button>
			{#if searchQuery}
				<button
					class="px-3 py-2 bg-surface-700 hover:bg-surface-600 text-text-secondary rounded-md text-sm transition-colors"
					onclick={() => { searchQuery = ''; searchResults = { songs: [], albums: [] }; }}
				>
					Clear
				</button>
			{/if}
		</div>
	</div>

	<!-- Search Results -->
	{#if searchResults.albums.length > 0 || searchResults.songs.length > 0}
		<div class="mb-8">
			<h3 class="text-lg font-medium text-text-primary mb-3">Search Results</h3>

			{#if searchResults.albums.length > 0}
				<div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
					{#each searchResults.albums as album}
						<button
							class="p-3 bg-surface-700 border border-border rounded-md hover:border-primary hover:bg-surface-600 transition-colors text-left"
							onclick={() => openAlbum(album.id)}
						>
							<p class="text-sm font-medium text-text-primary truncate">{album.name || 'Unknown'}</p>
							<p class="text-xs text-text-muted truncate">{album.artist || ''}</p>
						</button>
					{/each}
				</div>
			{/if}

			{#if searchResults.songs.length > 0}
				<div class="bg-surface-700 border border-border rounded-md overflow-hidden">
					{#each searchResults.songs as song, i}
						<div class="flex items-center justify-between px-4 py-2 {i < searchResults.songs.length - 1 ? 'border-b border-border' : ''}">
							<div class="flex-1 min-w-0">
								<p class="text-sm text-text-primary truncate">{song.title}</p>
								<p class="text-xs text-text-muted truncate">{song.artist || ''} — {song.album || ''}</p>
							</div>
							<div class="flex items-center gap-3 ml-4">
								<span class="text-xs text-text-muted mono">{formatDuration(song.duration)}</span>
								{#if song.path}
									<button
										class="text-xs text-error hover:text-red-400 transition-colors {confirmDelete === song.path ? 'font-bold' : ''}"
										onclick={() => confirmDelete === song.path ? deleteFile(song.path!) : (confirmDelete = song.path ?? null)}
										disabled={deleting === song.path}
									>
										{confirmDelete === song.path ? '✓ Confirm?' : '🗑'}
									</button>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Album Detail -->
	{#if selectedAlbum}
		<div class="mb-8">
			<div class="flex items-center justify-between mb-4">
				<div>
					<button
						class="text-sm text-text-muted hover:text-text-primary transition-colors mb-1"
						onclick={() => { selectedAlbum = null; }}
					>
						← Back to albums
					</button>
					<h3 class="text-xl font-semibold text-text-primary">{selectedAlbum.name}</h3>
					<p class="text-sm text-text-secondary">{selectedAlbum.artist}</p>
				</div>
				<div class="flex gap-2">
					{#if selectedAlbum.songs.length > 0 && selectedAlbum.songs[0].path}
						{@const dirPath = selectedAlbum.songs[0].path.split('/').slice(0, -1).join('/')}
						<button
							class="px-3 py-1.5 bg-error/10 border border-error/30 text-error rounded-md text-sm hover:bg-error/20 transition-colors"
							onclick={() => confirmDelete === selectedAlbum!.id ? deleteAlbumDirectory(dirPath) : (confirmDelete = selectedAlbum!.id)}
							disabled={deleting === dirPath}
						>
							{confirmDelete === selectedAlbum.id ? '⚠️ Confirm delete entire album?' : '🗑 Delete Album'}
						</button>
					{/if}
				</div>
			</div>

			<!-- Track list -->
			<div class="bg-surface-700 border border-border rounded-md overflow-hidden">
				{#each selectedAlbum.songs as song, i}
					<div class="flex items-center justify-between px-4 py-2 {i < selectedAlbum.songs.length - 1 ? 'border-b border-border' : ''}">
						<div class="flex-1 min-w-0">
							<span class="text-xs text-text-muted mono mr-3">{String(i + 1).padStart(2, '0')}</span>
							<span class="text-sm text-text-primary">{song.title}</span>
						</div>
						<div class="flex items-center gap-3">
							<span class="text-xs text-text-muted mono">{formatDuration(song.duration)}</span>
							{#if song.path}
								<button
									class="text-xs text-error hover:text-red-400 transition-colors {confirmDelete === song.path ? 'font-bold' : ''}"
									onclick={() => confirmDelete === song.path ? deleteFile(song.path!) : (confirmDelete = song.path ?? null)}
									disabled={deleting === song.path}
								>
									{confirmDelete === song.path ? '✓ Confirm?' : '🗑'}
								</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Album Grid (default view) -->
	{#if !selectedAlbum && searchResults.albums.length === 0 && searchResults.songs.length === 0}
		{#if loading}
			<p class="text-text-secondary">Loading albums...</p>
		{:else if albums.length === 0}
			<div class="text-center py-12">
				<p class="text-text-muted">No albums found. Make sure Navidrome is configured in Settings.</p>
			</div>
		{:else}
			<h3 class="text-lg font-medium text-text-primary mb-3">Albums</h3>
			<div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
				{#each albums as album}
					<button
						class="p-3 bg-surface-700 border border-border rounded-md hover:border-primary hover:bg-surface-600 transition-colors text-left"
						onclick={() => openAlbum(album.id)}
					>
						<p class="text-sm font-medium text-text-primary truncate">{album.name || 'Unknown'}</p>
						<p class="text-xs text-text-muted truncate">{album.artist || ''}</p>
						{#if album.songCount}
							<p class="text-xs text-text-muted mt-1">{album.songCount} tracks</p>
						{/if}
					</button>
				{/each}
			</div>
		{/if}
	{/if}
</div>