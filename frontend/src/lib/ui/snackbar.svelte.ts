import { writable } from 'svelte/store';

export type SnackbarKind = 'success' | 'error' | 'info';

export interface SnackbarItem {
	id: number;
	kind: SnackbarKind;
	text: string;
}

let nextId = 0;

function createSnackbar() {
	const { subscribe, update } = writable<SnackbarItem[]>([]);

	return {
		subscribe,
		notify(kind: SnackbarKind, text: string, duration = 6000): void {
			const id = ++nextId;
			update((items) => [...items, { id, kind, text }]);
			if (duration > 0) {
				setTimeout(() => {
					update((items) => items.filter((item) => item.id !== id));
				}, duration);
			}
		},
		close(id: number): void {
			update((items) => items.filter((item) => item.id !== id));
		}
	};
}

export const snackbar = createSnackbar();
