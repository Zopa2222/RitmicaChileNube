import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export type RutValidationCode = 'format' | 'checkDigit';

export function normalizeRut(value: unknown): string {
    return String(value ?? '')
        .trim()
        .toLocaleUpperCase('es-CL')
        .replace(/[^0-9K]/g, '');
}

export function rutValidationCode(value: unknown): RutValidationCode | null {
    const rut = normalizeRut(value);
    if (!/^\d{6,8}[0-9K]$/.test(rut)) {
        return 'format';
    }

    let factor = 2;
    let total = 0;
    for (const digit of rut.slice(0, -1).split('').reverse()) {
        total += Number(digit) * factor;
        factor = factor === 7 ? 2 : factor + 1;
    }
    const remainder = 11 - (total % 11);
    const expected = remainder === 11 ? '0' : remainder === 10 ? 'K' : String(remainder);
    return rut.at(-1) === expected ? null : 'checkDigit';
}

export function formatRut(value: unknown): string {
    const rut = normalizeRut(value);
    if (!rut) return '';
    const body = rut.slice(0, -1);
    const checkDigit = rut.slice(-1);
    return `${formatRutBody(body)}-${checkDigit}`;
}

/**
 * Formats a RUT while it is being typed. Eight unseparated characters are
 * treated as a seven-digit body plus check digit; nine are treated as an
 * eight-digit body plus check digit. A hyphen keeps the boundary explicit.
 */
export function formatRutInput(value: unknown): string {
    const raw = String(value ?? '').toLocaleUpperCase('es-CL');
    const dashIndex = raw.indexOf('-');

    if (dashIndex >= 0) {
        const body = raw.slice(0, dashIndex).replace(/\D/g, '').slice(0, 8);
        const trailingCharacters = raw.slice(dashIndex + 1).replace(/[^0-9K]/g, '');
        const checkDigit = trailingCharacters.slice(0, 1);

        // If a short RUT was auto-formatted after its eighth character, allow
        // the user to continue typing an eight-digit body and its check digit.
        if (body.length === 7 && trailingCharacters.length > 1) {
            const continuedRut = body + trailingCharacters;
            return `${formatRutBody(continuedRut.slice(0, 8))}-${continuedRut.slice(8, 9)}`;
        }
        return `${formatRutBody(body)}-${checkDigit}`;
    }

    const unseparatedRut = raw.replace(/[^0-9K]/g, '');
    if (unseparatedRut.length === 8) {
        return `${formatRutBody(unseparatedRut.slice(0, 7))}-${unseparatedRut.slice(7)}`;
    }

    let body = '';
    let checkDigit = '';
    for (const character of raw) {
        if (/\d/.test(character) && body.length < 8) {
            body += character;
        } else if (
            body.length === 8
            && !checkDigit
            && /[0-9K]/.test(character)
        ) {
            checkDigit = character;
        }
    }
    return checkDigit
        ? `${formatRutBody(body)}-${checkDigit}`
        : formatRutBody(body);
}

function formatRutBody(body: string): string {
    return body.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

export const rutValidator: ValidatorFn = (
    control: AbstractControl
): ValidationErrors | null => {
    const value = String(control.value ?? '').trim();
    if (!value) return null;
    const code = rutValidationCode(value);
    return code ? { rut: code } : null;
};
