// BEGIN
// Backwards compatible via ES5

// Show the popup window on select pages page
var popShow = function() {
  
  // USER ADJUSTED VARS:
  //--------------------
  // Either pass course path info to survey or not (1= enable, 0= disable); Used to determine which course respondents replied from.
  var popCrs = 0; 
  // Message to display inside div
  var popMsg = "Are you finding what you are looking for?";
  // Link to survey, form, mailto, etc.
  var surveyURL = "mailto:rctle@erau.edu?subject=Faculty Assistance&body=Hello, I need some guidance. Can we schedule a time to connect?";
  // Text displayed on popup button linking out
  var popBtnTxt = "No";
  // Timeout in ms (e.g., 1000ms = 1 seconds)
  var popDelay = 1000;
  // Display popup throughout course or just dashboard (0=disable, 1=enable)
  var popWhere = 0;

  // DON'T CHANGE ITEMS BELOW THIS LINE
  //-----------------------------------
  var { pathname } = window.location;
  
  // HTML to display
  var popHTML = "";
  var popURL = "";
  // Adjust popURL add/drop course path
  popURL = popCrs === 1 ? surveyURL + "?Course=" + window.location.pathname : surveyURL;

  // Determine where to display the popup (e.g., home page, or everywhere)
  if (popWhere === 1 ? pathname.match(/^\/courses\/\d+$/) : pathname.match(/^\/courses\/\d+(?:\/(?:modules|pages|assignments|syllabus|announcements|discussion_topics)(?:\/.+)?)?$/)) {
    popHTML = "<div class=\"container-footnote\" id=\"popDiv\" style=\"display:inline\">";
    popHTML += "<button type=\"button\" role=\"button\" class=\"close-button\" onclick=\"ClosePop()\">";
    popHTML += "<span class=\"hidden\">Close</span>";
    popHTML += "</button>";
    popHTML += "<h2><div class=\"eagleSVG\"></div></h2>";
    popHTML += "<div class=\"survey-content\" id=\"survey-content-text\"><span>"+popMsg+"</span>";
    popHTML += "<a class=\"button\" role=\"button\" id=\"QualtricsSurvey\" href=\""+popURL+"\" target=\"new\">"+popBtnTxt+"</a>";
    popHTML += "</div></div>";

    // Timer to set length of delay before popup appears, default is 1s
    setTimeout(function(){
      $('body').append(popHTML);
    },popDelay);
    window.focus();
  }
};

// Hide popup when close button is selected
var ClosePop = function() {
  var container = $('container-footnote');
  $('.container-footnote').addClass( "hidden" );
};

$(document).ready(function () {popShow();});

