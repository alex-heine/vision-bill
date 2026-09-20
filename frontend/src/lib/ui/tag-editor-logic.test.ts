import { describe, expect, it } from 'vitest';
import { buildTagRows, filterTags, moveActiveIndex, normalizeTag } from './tag-editor-logic';

const OPTIONS = [
	{ name: 'alcohol', system: true },
	{ name: 'beverage', system: true },
	{ name: 'coffee', system: true },
	{ name: 'food', system: true },
	{ name: 'fresh', system: true },
	{ name: 'household', system: true }
];

describe('normalizeTag', () => {
	it('trims, collapses whitespace, lowercases', () => {
		expect(normalizeTag('  Food   ITEM ')).toBe('food item');
		expect(normalizeTag('')).toBe('');
		expect(normalizeTag('already')).toBe('already');
	});
});

describe('filterTags', () => {
	it('returns everything (in order) for an empty query', () => {
		expect(filterTags(OPTIONS, '')).toEqual(OPTIONS);
	});

	it('matches case-insensitively on substrings', () => {
		expect(filterTags(OPTIONS, 'F')).toEqual([
			{ name: 'coffee', system: true },
			{ name: 'food', system: true },
			{ name: 'fresh', system: true }
		]);
		expect(filterTags(OPTIONS, 'ou')).toEqual([{ name: 'household', system: true }]);
	});

	it('returns nothing when nothing matches', () => {
		expect(filterTags(OPTIONS, 'veggie')).toEqual([]);
	});
});

describe('buildTagRows', () => {
	it('renders an empty hint when the vocabulary is empty', () => {
		expect(buildTagRows([], '', [])).toEqual([{ kind: 'empty' }]);
	});

	it('lists all options with sequential optionIndex, selection state and system flag', () => {
		expect(buildTagRows(OPTIONS, '', ['food'])).toEqual([
			{ kind: 'tag', tag: 'alcohol', system: true, selected: false, optionIndex: 0 },
			{ kind: 'tag', tag: 'beverage', system: true, selected: false, optionIndex: 1 },
			{ kind: 'tag', tag: 'coffee', system: true, selected: false, optionIndex: 2 },
			{ kind: 'tag', tag: 'food', system: true, selected: true, optionIndex: 3 },
			{ kind: 'tag', tag: 'fresh', system: true, selected: false, optionIndex: 4 },
			{ kind: 'tag', tag: 'household', system: true, selected: false, optionIndex: 5 }
		]);
	});

	it('filters by the query and keeps selection state (no create row while matches exist)', () => {
		expect(buildTagRows(OPTIONS, 'f', ['food'])).toEqual([
			{ kind: 'tag', tag: 'coffee', system: true, selected: false, optionIndex: 0 },
			{ kind: 'tag', tag: 'food', system: true, selected: true, optionIndex: 1 },
			{ kind: 'tag', tag: 'fresh', system: true, selected: false, optionIndex: 2 }
		]);
	});

	it('omits the create row while the query still matches options', () => {
		expect(buildTagRows(OPTIONS, 'foo', [])).toEqual([
			{ kind: 'tag', tag: 'food', system: true, selected: false, optionIndex: 0 }
		]);
	});

	it('omits the create row on exact match', () => {
		expect(buildTagRows(OPTIONS, 'FOOD', [])).toEqual([
			{ kind: 'tag', tag: 'food', system: true, selected: false, optionIndex: 0 }
		]);
	});

	it('shows a no-match hint above the create row when nothing matches', () => {
		expect(buildTagRows(OPTIONS, 'veggie', [])).toEqual([
			{ kind: 'nomatch', query: 'veggie' },
			{ kind: 'create', tag: 'veggie', optionIndex: 0 }
		]);
	});

	it('preserves system flag for mixed GPC and user tags', () => {
		const mixed = [
			{ name: 'milk', system: true },
			{ name: 'bread', system: true },
			{ name: 'my-custom', system: false }
		];
		expect(buildTagRows(mixed, '', [])).toEqual([
			{ kind: 'tag', tag: 'milk', system: true, selected: false, optionIndex: 0 },
			{ kind: 'tag', tag: 'bread', system: true, selected: false, optionIndex: 1 },
			{ kind: 'tag', tag: 'my-custom', system: false, selected: false, optionIndex: 2 }
		]);
	});
});

describe('moveActiveIndex', () => {
	it('wraps forward and backward', () => {
		expect(moveActiveIndex(3, 0, 1)).toBe(1);
		expect(moveActiveIndex(3, 2, 1)).toBe(0);
		expect(moveActiveIndex(3, 0, -1)).toBe(2);
		expect(moveActiveIndex(3, 1, -1)).toBe(0);
	});

	it('starts at the first or last row from no selection', () => {
		expect(moveActiveIndex(3, -1, 1)).toBe(0);
		expect(moveActiveIndex(3, -1, -1)).toBe(2);
	});

	it('returns -1 when there is nothing to select', () => {
		expect(moveActiveIndex(0, -1, 1)).toBe(-1);
		expect(moveActiveIndex(0, 0, -1)).toBe(-1);
	});
});
