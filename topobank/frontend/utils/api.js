export function subjectsToBase64(subjects) {
    return btoa(JSON.stringify(subjects));
}
