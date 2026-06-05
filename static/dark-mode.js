// Shared Dark Mode Toggle Script
document.addEventListener('DOMContentLoaded', function() {
    const darkModeBtn = document.getElementById('darkModeBtn');
    const themeText = document.getElementById('themeText');
    
    // Check for saved theme preference or default to light mode
    const currentTheme = localStorage.getItem('theme') || 'light';
    
    // Apply saved theme on page load
    if (currentTheme === 'dark') {
        document.body.classList.add('dark-mode');
        updateButtonText(true);
    }

    // Add click event listener if button exists
    if (darkModeBtn) {
        darkModeBtn.addEventListener('click', toggleDarkMode);
    }
});
if (currentTheme === 'dark') {
    document.body.classList.add('dark-mode');
    updateButtonText(true);
} else {
    updateButtonText(false);
}

function toggleDarkMode() {
    const isDarkMode = document.body.classList.toggle('dark-mode');
    
    if (isDarkMode) {
        localStorage.setItem('theme', 'dark');
        updateButtonText(true);
    } else {
        localStorage.setItem('theme', 'light');
        updateButtonText(false);
    }
}

function updateButtonText(isDark) {
    const darkModeBtn = document.getElementById('darkModeBtn');
    if (darkModeBtn) {
        if (isDark) {
            darkModeBtn.innerHTML = '<i class="fas fa-sun me-2"></i><span id="themeText">Light</span>';
        } else {
            darkModeBtn.innerHTML = '<i class="fas fa-moon me-2"></i><span id="themeText">Dark</span>';
        }
    }
}
