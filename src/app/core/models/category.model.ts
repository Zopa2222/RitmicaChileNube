import { Gymnast } from './gymnast.model';

// Category interface
export interface Category {
    id?: string;
    name: string;
    gymnasts: Gymnast[];
    championshipId?: string;
}

// Create empty category
export function createEmptyCategory(name: string): Category {
    return {
        name,
        gymnasts: []
    };
}
