// Helper to display errors
function displayError(errorContainer, message) {
    // console.log("Adding error message: " + message);
    errorContainer.append(`<p class="text-danger">${message}</p>`);
}

// Helper function to verify that all strings in the array are English characters
function verifyEnglishCharacters(array) {
    return array.every(function(str) {
        return /^[A-Za-z\s-,]+$/.test(str);
    });
}

// Function that gets the value of an input field using jQuery, verifies that there is a value, and if so splits the values out into an array
function getInputValue(inputField, emptyAllowed) {
    const inputArray = [];
    $(inputField).find('option:selected').each(function() {
        const locationText = $(this).val().trim();
        inputArray.push(locationText);
    }).get();
    console.log("Input array: '" + inputArray + "'")
    if (emptyAllowed && inputArray.length === 0) {
        return inputArray;
    }
    if (inputArray.length === 0) {
        return null;
    }    
    if (!verifyEnglishCharacters(inputArray)) {
        return null;
    }
    return inputArray
}

function getKeywordWeights(keywordWeightsErrorContainer) {
    const keywordWeights = {};
    $('#keywordTable tbody tr').each(function() {
        const keywordInput = $(this).find('input[type="text"]');
        const weightInput = $(this).find('input[type="number"]');
        const keyword = keywordInput.val().trim();
        const weight = parseInt(weightInput.val(), 10);
        // Validations
        if (!verifyEnglishCharacters([keyword])) {
            displayError(keywordWeightsErrorContainer, "'" + keyword + "' is not a valid keyword. Keywords must be English characters.");
            return -1;
        }
        if (isNaN(weight)) {
            displayError(keywordWeightsErrorContainer, "'" + weight + "' is not a valid weight. Weights must be integers.");
            return -1;
        }
        if (keyword in keywordWeights) {
            displayError(keywordWeightsErrorContainer, "'" + keyword + "' is a duplicate keyword. Please provide a unique keyword.");
            return -1;
        }
        // Add to keywordWeights
        keywordWeights[keyword] = weight;
    });
    return keywordWeights;
}

function validateCustomizationsForm(event) {
    // Prevent default form submission behavior
    event.preventDefault();

    // We assume all input is invalid until proven otherwise 
    let isValid = true;

    // The id of the div that will contain the error messages
    const searchTermErrorContainer = $('#search-terms-error-container');
    searchTermErrorContainer.empty();
    const searchLocationErrorContainer = $('#search-location-error-container');
    searchLocationErrorContainer.empty();
    const excludedLocationsErrorContainer = $('#excluded-locations-error-container');
    excludedLocationsErrorContainer.empty();
    const excludedIndustriesErrorContainer = $('#excluded-industries-error-container');
    excludedIndustriesErrorContainer.empty();
    const excludedCompaniesErrorContainer = $('#excluded-companies-error-container');
    excludedCompaniesErrorContainer.empty();
    const excludedJobTitlesErrorContainer = $('#excluded-job-titles-error-container');
    excludedJobTitlesErrorContainer.empty();
    const keywordWeightsErrorContainer = $('#keyword-weights-error-container');
    keywordWeightsErrorContainer.empty();
    const minGoodResultsErrorContainer = $('#minimum-good-results-error-container');
    minGoodResultsErrorContainer.empty();
    
    // The values of all the items in our forum
    const searchTerms = getInputValue('#search_terms', false);
    const searchLocations = getInputValue('#search_locations', false);
    const excludedLocations = getInputValue('#excluded_locations', true);
    const excludedIndustries = getInputValue('#excluded_industries', true);
    const excludedCompanies = getInputValue('#excluded_companies', true);
    const excludedJobTitles = getInputValue('#excluded_job_titles', true);
    const keywordWeights = getKeywordWeights(keywordWeightsErrorContainer);
    const minimum_good_results = parseInt($('#minimum_good_results_per_search_per_location').val(), 10);
    const includeHybridJobs = $('#include_hybrid_jobs').is(':checked');
    const experienceLevels = {
        "Associate": true,
        "Director": false,
        "Entry level": true,
        "Internship": false,
        "Mid-Senior level": true
    };

    if (!searchTerms) {
        displayError(searchTermErrorContainer, "Must provide at least one search term and all search terms must be English characters.");
        isValid = false;
    }
    if (!searchLocations) {
        displayError(searchLocationErrorContainer, "Must provide at least one location and all locations must be English characters.");
        isValid = false;
    }
    if (!excludedLocations) {
        displayError(excludedLocationsErrorContainer, "All excluded locations must be English characters.");
        isValid = false;
    }
    if (!excludedIndustries) {
        displayError(excludedIndustriesErrorContainer, "All excluded industries must be English characters.");
        isValid = false;
    }
    if (!excludedCompanies) {
        displayError(excludedCompaniesErrorContainer, "All excluded companies must be English characters.");
        isValid = false;
    }
    if (!excludedJobTitles) {
        displayError(excludedJobTitlesErrorContainer, "All excluded job titles must be English characters.");
        isValid = false;
    }
    if (isNaN(minimum_good_results) || minimum_good_results <= 0) {
        displayError(minGoodResultsErrorContainer, "'" + minimum_good_results + "' is not a valid minimum good results value. Please provide a positive integer.");
        isValid = false;
    }
    if (keywordWeights === -1) {
        isValid = false;
    }

    if (!isValid) {
        return isValid;
    }
    console.log("All input is valid constructing our customizations JSON object")
    const customizations = {
        searches: [...new Set(searchTerms)],
        locations: [...new Set(searchLocations)],
        excluded_locations: [...new Set(excludedLocations)],
        excluded_industries: [...new Set(excludedIndustries)],
        excluded_companies: [...new Set(excludedCompanies)],
        excluded_title_keywords: [...new Set(excludedJobTitles)],
        word_weights: keywordWeights,
        minimum_good_results_per_search_per_location: minimum_good_results,
        include_hybrid_jobs: includeHybridJobs,
        experience_levels: experienceLevels
    };
    console.log("Posting customizations to the server")
    console.log(customizations)
    var jq = $.noConflict();
    jq.ajax({
        url: '/save_customizations',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(customizations),
        success: function(response) {
            console.log("Success:", response);
            window.location.href = '/customizations';
        },
        error: function(error) {
            console.error("Error:", error);
        }
    });
    return isValid;
}
