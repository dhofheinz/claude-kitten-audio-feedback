// Repository configuration - change this when forking
const REPO_CONFIG = {
    owner: 'dhofheinz',
    repo: 'claude-kitten-audio-feedback',
    get url() {
        return `https://github.com/${this.owner}/${this.repo}`;
    },
    get cloneUrl() {
        return `${this.url}.git`;
    }
};

// Export for use in the page
if (typeof window !== 'undefined') {
    window.REPO_CONFIG = REPO_CONFIG;
}