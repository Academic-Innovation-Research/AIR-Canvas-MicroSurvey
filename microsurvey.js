// Canvas Popup/Button Display Script
// This script allows for displaying either a popup or a button in Canvas LMS

(function() {
  // USER ADJUSTED VARS:
  //--------------------
  // Display type: 0 = popup, 1 = button in sidebar
  var displayType = 0; 
  
  // Either pass course path info to survey or not (1= enable, 0= disable)
  var popCrs = 1; 
  
  // Message to display inside popup div
  var popMsg = "Share Your Thoughts";
  
  // Link to survey, form, mailto, etc.
  var surveyURL = "https://erau.qualtrics.com/jfe/form/SV_7VOlXPhXxcfCU2q";
  
  // Text displayed on popup button linking out
  var popBtnTxt = "Yes";
  
  // Button text if using sidebar button
  var sidebarBtnText = "Share Your Thoughts";
  
  // Button background color (for sidebar button)
  var btnBgColor = "#993333";
  
  // Button text color (for sidebar button)
  var btnTextColor = "#fff";
  
  // Timeout in ms before popup appears (e.g., 1000ms = 1 second)
  var popDelay = 1000;
  
  // Display popup throughout course or just specific pages (0=specific pages, 1=home page only)
  var popWhere = 0;
  
  // DON'T CHANGE ITEMS BELOW THIS LINE
  //-----------------------------------
  
  // Function to show popup
  var popShow = function() {
    var { pathname } = window.location;
    
    // HTML to display
    var popHTML = "";
    var popURL = "";
    
    // Adjust popURL add/drop course path
    popURL = popCrs === 1 ? surveyURL + "?Course=" + window.location.pathname : surveyURL;
    
    // Determine where to display the popup
    var showOnPage = false;
    if (popWhere === 1) {
      // Show only on course home page
      showOnPage = pathname.match(/^\/courses\/\d+$/);
    } else {
      // Show on course home, modules, pages, assignments, syllabus, announcements, discussions
      showOnPage = pathname.match(/^\/courses\/\d+(?:\/(?:modules|pages|assignments|syllabus|announcements|discussion_topics)(?:\/.+)?)?$/);
    }
    
    if (showOnPage) {
      popHTML = "<div class=\"container-footnote\" id=\"popDiv\" style=\"display:inline\">";
      popHTML += "<button type=\"button\" role=\"button\" class=\"close-button\" onclick=\"ClosePop()\">";
      popHTML += "<span class=\"hidden\">Close</span>";
      popHTML += "</button>";
      popHTML += "<h2><div class=\"eagleSVG\"></div></h2>";
      popHTML += "<div class=\"survey-content\" id=\"survey-content-text\"><span>"+popMsg+"</span>";
      popHTML += "<a class=\"button\" role=\"button\" id=\"QualtricsSurvey\" href=\""+popURL+"\" target=\"new\">"+popBtnTxt+"</a>";
      popHTML += "</div></div>";
      
      // Timer to set length of delay before popup appears
      setTimeout(function(){
        $('body').append(popHTML);
      }, popDelay);
      
      window.focus();
    }
  };
  
  // Function to hide popup when close button is selected
  var ClosePop = function() {
    $('.container-footnote').addClass("hidden");
  };
  
  // Function to add button to sidebar
  var addSidebarButton = function() {
    // Create direct link button HTML
    var buttonHTML = '<a class="Button Button--primary Button--block" role="button" href="' + surveyURL + "?Course=" + window.location.pathname + '" ' +
                    'target="_blank" style="background: ' + btnBgColor + '; color: ' + btnTextColor + ';">' + 
                    sidebarBtnText + '</a>';
    
  // Check if course_show_secondary div exists
    if ($('#course_show_secondary').length) {
      // Add button as the first element inside course_show_secondary
      $('#course_show_secondary').prepend(buttonHTML);
    } else {
      // Fallback to right-side if course_show_secondary doesn't exist
      $('#right-side').prepend(buttonHTML);
    }
  };
    
  // On document ready, initialize the selected display type
  $(document).ready(function() {
    if (displayType === 0) {
      // Initialize popup
      popShow();
      
      // Add global ClosePop function
      window.ClosePop = ClosePop;
    } else {
      // Initialize sidebar button
      addSidebarButton();
    }
  });
})();