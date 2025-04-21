// static/js/search_form.js

/**
 * Enhanced search functionality with autocomplete
 * for the Lobbying Disclosure App
 */

document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const searchForm = document.getElementById('searchForm');
    const nameField = document.getElementById('name');
    const companyField = document.getElementById('company');
    const issueAreaField = document.getElementById('issue_area');
    const agencyField = document.getElementById('agency');
    const dataSourceField = document.getElementById('data_source');
    
    // Suggestion containers
    const nameSuggestions = document.getElementById('name-suggestions');
    const companySuggestions = document.getElementById('company-suggestions');
    const agencySuggestions = document.getElementById('agency-suggestions');
    
    // Search history
    let searchHistory = JSON.parse(localStorage.getItem('searchHistory') || '{"names": [], "companies": [], "agencies": []}');
    
    // Common agencies for autocomplete
    const commonAgencies = [
        "Department of Defense (DOD)",
        "Environmental Protection Agency (EPA)",
        "Federal Communications Commission (FCC)",
        "Department of Health and Human Services (HHS)",
        "Centers for Medicare & Medicaid Services (CMS)",
        "Food and Drug Administration (FDA)",
        "Department of Energy (DOE)",
        "Department of Transportation (DOT)",
        "Department of Homeland Security (DHS)",
        "Department of Justice (DOJ)",
        "Department of Agriculture (USDA)",
        "Department of Commerce (DOC)",
        "Department of Education (ED)",
        "Department of Labor (DOL)",
        "Department of State (DOS)",
        "Department of the Treasury",
        "Department of Veterans Affairs (VA)",
        "Federal Trade Commission (FTC)",
        "Securities and Exchange Commission (SEC)",
        "Internal Revenue Service (IRS)",
        "National Institutes of Health (NIH)",
        "Centers for Disease Control (CDC)",
        "Federal Aviation Administration (FAA)",
        "Federal Emergency Management Agency (FEMA)",
        "Consumer Financial Protection Bureau (CFPB)",
        "National Science Foundation (NSF)"
    ];
    
    /**
     * Save search to history
     * @param {string} type - Type of search (names, companies, agencies)
     * @param {string} value - Search value
     */
    function saveToHistory(type, value) {
        if (!value.trim()) return;
        
        // Add to beginning of array, remove duplicates
        searchHistory[type] = [
            value,
            ...searchHistory[type].filter(item => item !== value)
        ].slice(0, 10); // Keep only 10 most recent
        
        localStorage.setItem('searchHistory', JSON.stringify(searchHistory));
    }
    
    /**
     * Create autocomplete functionality for input field
     * @param {HTMLElement} inputField - The input field
     * @param {HTMLElement} suggestionsContainer - The suggestions container
     * @param {Array} suggestions - Array of suggestion items
     * @param {Function} filterFunction - Custom filter function
     */
    function setupAutocomplete(inputField, suggestionsContainer, suggestions, filterFunction) {
        if (!inputField || !suggestionsContainer) return;
        
        // Event listeners
        inputField.addEventListener('input', function() {
            const inputValue = this.value.trim();
            
            // Clear suggestions if input is empty
            if (!inputValue) {
                suggestionsContainer.innerHTML = '';
                suggestionsContainer.style.display = 'none';
                return;
            }
            
            // Filter suggestions
            const filteredSuggestions = filterFunction(inputValue, suggestions);
            
            // Display suggestions
            if (filteredSuggestions.length > 0) {
                suggestionsContainer.innerHTML = '';
                
                filteredSuggestions.forEach(function(suggestion) {
                    const item = document.createElement('div');
                    item.className = 'suggestion-item';
                    item.textContent = suggestion;
                    
                    item.addEventListener('click', function() {
                        inputField.value = suggestion;
                        suggestionsContainer.innerHTML = '';
                        suggestionsContainer.style.display = 'none';
                    });
                    
                    suggestionsContainer.appendChild(item);
                });
                
                suggestionsContainer.style.display = 'block';
            } else {
                suggestionsContainer.innerHTML = '';
                suggestionsContainer.style.display = 'none';
            }
        });
        
        // Hide suggestions when clicking outside
        document.addEventListener('click', function(e) {
            if (e.target !== inputField && e.target !== suggestionsContainer) {
                suggestionsContainer.style.display = 'none';
            }
        });
        
        // Focus and keydown events
        inputField.addEventListener('focus', function() {
            if (this.value.trim() && suggestionsContainer.children.length > 0) {
                suggestionsContainer.style.display = 'block';
            }
        });
        
        inputField.addEventListener('keydown', function(e) {
            if (suggestionsContainer.style.display === 'block') {
                const items = suggestionsContainer.querySelectorAll('.suggestion-item');
                let focusedIndex = Array.from(items).findIndex(item => item.classList.contains('focused'));
                
                // Arrow down
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (focusedIndex < items.length - 1) {
                        if (focusedIndex >= 0) items[focusedIndex].classList.remove('focused');
                        items[focusedIndex + 1].classList.add('focused');
                    } else if (focusedIndex === -1 && items.length > 0) {
                        items[0].classList.add('focused');
                    }
                }
                
                // Arrow up
                else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (focusedIndex > 0) {
                        items[focusedIndex].classList.remove('focused');
                        items[focusedIndex - 1].classList.add('focused');
                    }
                }
                
                // Enter
                else if (e.key === 'Enter') {
                    if (focusedIndex >= 0) {
                        e.preventDefault();
                        inputField.value = items[focusedIndex].textContent;
                        suggestionsContainer.style.display = 'none';
                    }
                }
                
                // Escape
                else if (e.key === 'Escape') {
                    suggestionsContainer.style.display = 'none';
                }
            }
        });
    }
    
    // Filter functions for different fields
    function filterNames(input, suggestions) {
        const lowerInput = input.toLowerCase();
        return suggestions.filter(name => name.toLowerCase().includes(lowerInput));
    }
    
    function filterCompanies(input, suggestions) {
        const lowerInput = input.toLowerCase();
        return suggestions.filter(company => company.toLowerCase().includes(lowerInput));
    }
    
    function filterAgencies(input, suggestions) {
        const lowerInput = input.toLowerCase();
        const matches = suggestions.filter(agency => {
            const lowerAgency = agency.toLowerCase();
            
            // Match at beginning of words or by acronym
            if (lowerAgency.startsWith(lowerInput)) return true;
            
            // Match by words
            const words = lowerAgency.split(' ');
            if (words.some(word => word.startsWith(lowerInput))) return true;
            
            // Match by acronym (in parentheses)
            const acronymMatch = lowerAgency.match(/\(([^)]+)\)/);
            if (acronymMatch && acronymMatch[1].toLowerCase().includes(lowerInput)) return true;
            
            // General includes
            return lowerAgency.includes(lowerInput);
        });
        
        return matches;
    }
    
    // Initialize autocomplete
    setupAutocomplete(nameField, nameSuggestions, searchHistory.names, filterNames);
    setupAutocomplete(companyField, companySuggestions, searchHistory.companies, filterCompanies);
    setupAutocomplete(agencyField, agencySuggestions, 
                     [...commonAgencies, ...searchHistory.agencies], filterAgencies);
    
    // Form submission handler
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            // Save search terms to history
            if (nameField.value.trim()) {
                saveToHistory('names', nameField.value.trim());
            }
            
            if (companyField.value.trim()) {
                saveToHistory('companies', companyField.value.trim());
            }
            
            if (agencyField.value.trim()) {
                saveToHistory('agencies', agencyField.value.trim());
            }
            
            // Continue with form submission
            return true;
        });
    }
    
    // Data source change handler
    if (dataSourceField) {
        dataSourceField.addEventListener('change', function() {
            // Show/hide data source specific fields or options
            const selectedSource = this.value;
            
            // Example: Show/hide NY-specific fields
            const nyFields = document.querySelectorAll('.ny-specific');
            nyFields.forEach(field => {
                field.style.display = (selectedSource === 'ny_state' || selectedSource === 'nyc') 
                    ? 'block' : 'none';
            });
            
            // Example: Update issue area options based on data source
            if (issueAreaField) {
                // This is just a placeholder - you would need to implement this
                // based on the actual issue areas for each data source
                console.log(`Data source changed to ${selectedSource}`);
            }
        });
        
        // Trigger change event on load to set initial state
        dataSourceField.dispatchEvent(new Event('change'));
    }
});