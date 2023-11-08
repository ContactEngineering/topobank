export function subjectsToBase64(subjects) {
    return btoa(JSON.stringify(subjects));
}

export function getIdFromUrl(url) {
    const s = url.split('/');
    return Number(s[s.length-2]);
}
