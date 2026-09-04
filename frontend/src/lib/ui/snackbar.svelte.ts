import { writable } from 'svelte/store';

export type SnackbarKind = 'success' | 'error' | 'info';

export interface SnackbarItem {
	id: string;
	kind: SnackbarKind;
	text: string;
}

function createSnackbar() {
	const { subscribe, update } = writable<SnackbarItem[]>([]);

	return {
		subscribe,
		notify(kind: SnackbarKind, text: string, duration = 6000): void {
			const id = crypto.randomUUID();
			update((items) => [...items, { id, kind, text }]);
			if (duration > 0) {
				setTimeout(() => {
					update((items) => items.filter((item) => item.id !== id));
				}, duration);
			}
		},
		close(id: string): void {
			update((items) => items.filter((item) => item.id !== id));
		}
	};
}

export const snackbar = createSnackbar();
