if (typeof onElementRendered === 'undefined') {
	function onElementRendered(selector, cb, _attempts) {
		var el = $(selector);
		_attempts = ++_attempts || 1;
		if (el.length) return cb(el); //if (_attempts == 60) return;
		setTimeout(function() {
			onElementRendered(selector, cb, _attempts);
		}, 250);
	}
}

$(document).ready(function() {
	if ($.inArray('admin', ENV.current_user_roles) === -1) {

	// NON-ADMINS only

	} else {

	// ADMINS ONLY

		// TEST ENVIRONMENT ONLY
		if (window.location.hostname === "erau.test.instructure.com") {
		}
		
		$('.choose_home_page_link').css('display', 'block');
		// Reveal Course Status (publish / unpublish feature)
		$('#course_status').css('display', 'block');

	}

	// EVERYONE
	
	$('.Reminder__course-setup-body').empty().append($('.Reminder__course-setup-subttitle').text());
	$('.Reminder__course-setup').css('display', 'block');

	// Add Hunt Library link / modal to Course navigation
	var hunt_library_modal = document.createElement( 'div' );
	$( hunt_library_modal ).html( '\
		<p>The Hunt Library is the Library for all Worldwide students regardless of&nbsp;location. For&nbsp;help, please contact <a target="_blank" href="http://guides.erau.edu/ask-a-librarian">Ask&nbsp;a&nbsp;Librarian</a>.</p>\
		<p><a class="btn btn-small btn-primary" target="_blank" href="http://huntlibrary.erau.edu/">Visit Hunt Library Website</a></p>\
		<ul>\
			<li><a target="_blank" href="http://guides.erau.edu/az.php">Research Databases</a></li>\
			<li><a target="_blank" href="http://guides.erau.edu/">Research Guides</a></li>\
			<li><a target="_blank" href="http://huntlibrary.erau.edu/help/library-tutorials">Library Tutorials</a></li>\
		</ul>\
	' );
	var hunt_library_button = document.createElement( 'li' );
	$( hunt_library_button ).html( '<a href="#" id="hunt-lib-button">Hunt Library</a>' );
	$( hunt_library_button ).find( 'a' ).click(function() {
		$( this ).blur();
		$( hunt_library_modal ).dialog({
			title: "Hunt Library",
			width: 400,
			resizable: !1
		});
		event.preventDefault();
		event.stopPropagation();
	});

	var section_tabs = $( '#section-tabs' );
	var last_section_tab = $( section_tabs ).children().last();

	if ( last_section_tab.text() == 'Settings' ) {
		last_section_tab.before( hunt_library_button );
	} else {
		section_tabs.append( hunt_library_button );
	}

	// Add Bookstore link / modal to Course navigation
	var bookstore_modal = document.createElement( 'div' );
	$( bookstore_modal ).html( '\
		<p>The <a href="//worldwide.erau.edu/search/textbook-materials-list/" target="_blank">Master Textbook & Materials list</a> provides the required textbooks and materials for Graduate and Undergraduate Worldwide courses. This information is updated 60 days prior to each term start date.</p>\
		<p>Visit the <a href="http://www.bkstr.com/erauworldwidestore/home" target="_blank">Worldwide Bookstore</a> to find textbook pricing and purchasing options.</p>\
	' );
	var bookstore_button = document.createElement( 'li' );
	$( bookstore_button ).html( '<a href="#" id="bookstore-button">Bookstore</a>' );
	$( bookstore_button ).find( 'a' ).click(function() {
		$( this ).blur();
		$( bookstore_modal ).dialog({
			title: "Bookstore",
			width: 400,
			resizable: !1
		});
		event.preventDefault();
		event.stopPropagation();
	});

	var section_tabs = $( '#section-tabs' );
	var last_section_tab = $( section_tabs ).children().last();

	if ( last_section_tab.text() == 'Settings' ) {
		last_section_tab.before( bookstore_button );
	} else {
		section_tabs.append( bookstore_button );
	}
	// ==================================================

	// Add eUnion link to Course navigation
	var eunion_button = document.createElement( 'li' );
	$( eunion_button ).html( '<a href="https://eunion.erau.edu" target="_blank" id="eunion-button">eUnion</a>' );

	var section_tabs = $( '#section-tabs' );
	var last_section_tab = $( section_tabs ).children().last();

	if ( last_section_tab.text() == 'Settings' ) {
		last_section_tab.before( eunion_button );
	} else {
		section_tabs.append( eunion_button );
	}
	// ==================================================

	// Add temporary "25 Years of Online Education" banner
	if ( typeof String.prototype.endsWith !== 'function' ) {
		String.prototype.endsWith = function( suffix ) {
			return this.indexOf( suffix, this.length - suffix.length ) !== -1;
		};
	}
	if ( true === ENV.COURSE_HOME && ( ENV.COURSE_TITLE.endsWith( ' - Online' ) || ENV.COURSE_TITLE.endsWith( ' Online (CEU)' ) )) {
		$( "#right-side" ).prepend( '<p style="text-align:center;"><a href="https://news.erau.edu/headlines/us-news-world-report-ranks-embry-riddle-no-1-for-online-bachelors-degrees-online-programs-for-vets" target="_blank"><img src="https:///erau.edu/-/media/images/university/homepage-hero-image/usnwr-2021-2-badges.png" alt="U.S. News & World Report Ranks Embry-Riddle No. 1 for Online Bachelor’s Degrees, Online Programs for Vets"></a></p>' ); 
	}

	// Customize Respondus LockDown Browser requirement page
	if ((window.location.pathname.substring(window.location.pathname.lastIndexOf('/') + 1)) == 'lockdown_browser_required') {
		$("#content").html('<h1>Respondus LockDown Browser Required</h1><div class="bg-primary" style="background:#FFFADF;padding:30px;"><div class="grid-row"><div class="col-xs-12 col-sm-7"><p>This quiz <strong>requires <a href="http://www.respondus.com/lockdown/download.php?id=267517570" target="_blank">Respondus LockDown Browser</a></strong>. To&nbsp;take this quiz or view your quiz results, launch Respondus LockDown Browser from the Desktop (Windows) or the Applications folder (Mac), log into Canvas, locate your course, and click the&nbsp;exam.</p></div><div class="col-xs-12 col-sm-5"><p><a class="Button Button--primary" href="http://www.respondus.com/lockdown/download.php?id=267517570" target="_blank">Download Respondus LockDown&nbsp;Browser</a></p><p><small>If you have not already installed the browser, please download using the&nbsp;button&nbsp;above.</small></p></div></div></div>');
	}

	// WW Hides "Share in Commons" links. That can result in empty dropdown menus. Add "Need Help" link if a menu would be empty.
	$(document).on('mousedown click keydown', '.al-trigger', function(event) {
		var dropdown = $(this).next('.al-options');
		var visible_links = dropdown.find('a').filter(function(){
			var display = $(this).css('display');
			return display !== 'none';
		});
		if (visible_links.length === 0) {
			dropdown.append('<li role="presentation" class="ui-menu-item"><a href="http://help.instructure.com/" class="menu_tool_link ui-corner-all" role="menuitem"><i class="icon-question"></i> Need help?</a></li>');
		}
	});

	////////////////////////////////////////////////////////////////
	// Add Email Advisor link to Gradebook (Student Context Tray) //
	////////////////////////////////////////////////////////////////

	if ($(document.body).hasClass('gradebook')) {
		// Only run on Gradebook or People pages
		// Delegated click event
		// New student names may be loaded asynchronously
		$(document.body).on('click', '.student_context_card_trigger', function(){

			var studentName = $(this).text();
			var canvasStudentId = $(this).attr('data-student_id');
			var canvasCourseId = $(this).attr('data-course_id');
			var teacherEmail = "";

			var contextTrayStudentLink = $('.StudentContextTray-Header__Name a');
			var thisStudentTrayOpen = false;
			
			if (contextTrayStudentLink.length) {
				var contextTrayStudentID = contextTrayStudentLink.attr('href').split('/').pop();
				if (canvasStudentId === contextTrayStudentID) {
					var thisStudentTrayOpen = true;
				}
			}

			// Cancel if Student Context Tray is already open for this student
			if (thisStudentTrayOpen === false) {	
				var studentAdvisorInfo = $.getJSON("https://webforms.erau.edu/common/services/student/studentprofile.cfc?method=getStudentProfileWS&canvasid="+canvasStudentId+"&returnformat=JSON");

				var teacherProfile = $.getJSON('/api/v1/courses/'+ canvasCourseId + '/users?enrollment_type[]=teacher');

				teacherProfile.success(function(teacher){
					if (teacher.length > 0 ) {
						teacherEmail = teacher[0].login_id;
					}
				});

				// Take a brief pause to wait for any open Student Context Tray to be closed
				setTimeout(function(){
					// Wait for Student Context Tray to open
					onElementRendered('.StudentContextTray', function(){

						var modalStudentName = $('.StudentContextTray-Header__Name').text();
						var quickLinks = $('.StudentContextTray-QuickLinks');

						// Create Loading indicator
						var contactAdvisorLoader = $(document.createElement('div'));
						contactAdvisorLoader.css({
							display: 'block',
							textAlign: 'center',
							paddingBottom: '12px'
						});
						contactAdvisorLoader.html('Advisor Data Loading <style>@keyframes loader-spin {0% {transform: rotate(0deg);}100% {transform: rotate(360deg);}}</style><div style="display: inline-block; position: relative; top: 4px; margin: 0; border: 3px solid #ddd; border-top: 3px solid #3a6fcd; border-radius: 50%; width: 16px; height: 16px; animation: loader-spin 1s linear infinite;"></div>');
						quickLinks.before(contactAdvisorLoader);

						studentAdvisorInfo.success(function(data){
							var contactAdvisorLink = $(document.createElement('div'));
							contactAdvisorLink.css({
								display: 'none',
								textAlign: 'center',
								paddingBottom: '12px',
								lineHeight: '1'
							});

							if ( (data.RESULT === 'success' || data.RESULT === 'partial' )
									//&& profile.short_name.trim() == modalStudentName.trim() 
								) {

								var advisorEmail = data.ADVISOR.DATA.ADVISOR_EMAIL;
								var TfaAdvisorLink = "https://erau.tfaforms.net/217864?STCSID=" + data.STUDENT.ERAUID + "&ERAUEmail=" + teacherEmail.replace("@", "%40") + "&LMSKEY=" + ENV.GRADEBOOK_OPTIONS.sections[0].sis_section_id + "_" + data.STUDENT.ERAUID + "&tfa_38=" + advisorEmail;

								contactAdvisorLink.html(
									$(document.createElement('a'))
										.css({
											display: 'block',
											padding: '9px',
											border: '1px solid',
											borderRadius: '4px',
											textDecoration: 'none'
										})
										.hover(function(e) {
											$(this).css("background-color",e.type === "mouseenter" ? "#ecf3fa" : "transparent") 
										})
										.attr('aria-label', 'Contact advisor for ' +studentName)
										.attr('href', TfaAdvisorLink)
									//	.attr('onclick', "ga('send', 'event', 'student-tray', 'link', 'Email Advisor', 1);")
										.attr('target', "_blank")
										.html('Contact Advisor')
										.append(' <i class="icon-email" aria-hidden="true" style="margin-left: 5px;"></i>')
								);

								if (teacherEmail == "") {
									contactAdvisorLink.html('<small><em>Teacher data unavailable, could not create Contact Advisor button.</em></small>');
								}
							}
							else {
								contactAdvisorLink.html('<small><em>Student Advisor Data Unavailable</em></small>');
							}
							quickLinks.before(contactAdvisorLink);
							contactAdvisorLink.slideDown('fast');
							contactAdvisorLoader.slideUp();
						});
					}, 6*1000);
				}, 1500);
			}
		});
	}

	////////////////////////////////////////////////////////////////////
	// Add Student Dashboard link to Gradebook (Student Context Tray) //
	////////////////////////////////////////////////////////////////////
	if ($(document.body).hasClass('gradebook') || $(document.body).hasClass('people')) {
		// Only run on Gradebook or People pages
		// Delegated click event
		// New student names may be loaded asynchronously
		$(document.body).on('click', '.student_context_card_trigger', function(){

			var studentName = $(this).text();
			var canvasStudentId = $(this).attr('data-student_id');
			var canvasCourseId = $(this).attr('data-course_id');

			var contextTrayStudentLink = $('.StudentContextTray-Header__Name a');
			var thisStudentTrayOpen = false;
			
			if (contextTrayStudentLink.length) {
				var contextTrayStudentID = contextTrayStudentLink.attr('href').split('/').pop();
				if (canvasStudentId === contextTrayStudentID) {
					var thisStudentTrayOpen = true;
				}
			}

			// Cancel if Student Context Tray is already open for this student
			if (thisStudentTrayOpen === false) {

				var dataGlobal;
	
				var cob_dashboardInfo = $.getJSON("https://webforms.erau.edu/common/services/student/studentprofile.cfc?method=getStudentProfileWS&canvasid="+canvasStudentId+"&courseid="+canvasCourseId+"&returnformat=JSON");

				function drawChart(type) {
					var chartLabels;
					var chartText;

					switch (type) {
						case 'overall':
							chartLabels = dataGlobal.CHARTDATA.OVERALL.LABELS
							chartDataLine = dataGlobal.CHARTDATA.OVERALL.AVGTAKERATEPERYEAR
							chartDataBar = dataGlobal.CHARTDATA.OVERALL.COURSESPERYEAR
							chartText = "Student Persistance History - Overall"
							break;
		
						case 'major':
							chartLabels = dataGlobal.CHARTDATA.MAJOR.LABELS
							chartDataLine = dataGlobal.CHARTDATA.MAJOR.AVGTAKERATEPERYEAR
							chartDataBar = dataGlobal.CHARTDATA.MAJOR.COURSESPERYEAR
							chartText = "Student Persistance History - Major"
							break;
					}
					var ChartData = {
						labels: chartLabels,
						datasets: [
						{
							type: 'line',
							fill: false,
							label: 'average take rate',
							backgroundColor: 'rgb(255, 193, 7)',
							borderColor: 'rgb(255, 193, 7)',
							data: chartDataLine
						},
						{
							type: 'bar',
							label: 'courses per year',
							backgroundColor: 'rgba(18, 106, 180, 1)',
							borderColor: 'rgb(18, 106, 180)',
							data: chartDataBar
						}]
					};

					var charObject = document.getElementById('chart').getContext('2d');
					var chart = new Chart(charObject, {
						// The type of chart we want to create
						type: 'bar',
			
						// The data for our dataset
						data: ChartData,
			
						// Configuration options go here
						options: { 
							title: {
								text: chartText,
								display: true
							},
							scales: {
								xAxes: [{
									display: true,
									scaleLabel: {
										display: true,
										labelString: 'Academic Year'
									}
								}],
								yAxes: [{
									ticks: {
										// forces step size to be 1 units
										stepSize: 1,
										suggestedMin: 0
									}
								}]
							}
						}
					});
				}
				// Take a brief pause to wait for any open Student Context Tray to be closed
				setTimeout(function(){
					// Wait for Student Context Tray to open
					onElementRendered('.StudentContextTray', function(){

						var modalStudentName = $('.StudentContextTray-Header__Name').text();
						var quickLinks = $('.StudentContextTray-QuickLinks');

						// Create Loading indicator
						var dashboardLoader = $(document.createElement('div'));
						dashboardLoader.css({
							display: 'block',
							textAlign: 'center',
							paddingBottom: '12px'
						});
						dashboardLoader.html('Student Dashboard Loading <style>@keyframes loader-spin {0% {transform: rotate(0deg);}100% {transform: rotate(360deg);}}</style><div style="display: inline-block; position: relative; top: 4px; margin: 0; border: 3px solid #ddd; border-top: 3px solid #3a6fcd; border-radius: 50%; width: 16px; height: 16px; animation: loader-spin 1s linear infinite;"></div>');
						quickLinks.before(dashboardLoader);

						cob_dashboardInfo.success(function(data){

							var dashboardLink = $(document.createElement('div'));
							dashboardLink.css({
								display: 'none',
								textAlign: 'center',
								paddingBottom: '12px'
							});
							dashboardLink.html(
								$(document.createElement('a'))
									.css({
										display: 'block',
										padding: '9px',
										border: '1px solid',
										borderRadius: '4px',
										textDecoration: 'none'
									})
									.hover(function(e) {
										$(this).css("background-color",e.type === "mouseenter" ? "#ecf3fa" : "transparent") 
									})
									.attr('aria-label', studentName + ' Profile')
									.attr('href', '#')
									.attr('onclick', "ga('create', 'UA-178123650-1', 'auto', {'name': 'CanvasTest','allowLinker': true }); ga('CanvasTest.send', 'event', 'student-tray', 'link', 'Student Dashboard', 1);")
									.html('Student Dashboard')
									.append('<i class="icon-analytics" aria-hidden="true" style="margin-left: 5px;"></i>')
							);
							quickLinks.before(dashboardLink);

							if ( (data.RESULT === 'success' || data.RESULT === 'partial' )
									//&& profile.short_name.trim() == modalStudentName.trim() 
								) {

								var advisorName = data.ADVISOR.DATA.ADVISOR_NAME;
								
								var cob_dashboard_modal = document.createElement( 'div' );
									cob_dashboard_modal.className = "cob-modal";
								
								var status 		= (data.STATUS == "GR") ? data.TOTALCREDITSEARNED : data.STATUS;
								var statusLabel = (data.STATUS == "GR") ? "Total Credits Earned" : "Status";
								
								if (data.TIMEINMAJOR == "" && data.MAJORTAKERATE == "") {
									$( cob_dashboard_modal ).html( '\
									<table class="table table-striped">\
									<tr><td>' + statusLabel + '</td><td>' + status + '</td></tr>\
									<tr><td>GPA</td><td>' + data.CGPU + ' <span style="float: right;">(class average: ' + data.CLASSAVGCGPU + ')</span></td></tr>\
									<tr><td>Degree Plan</td><td>' + data.DEGREEPLAN + '</td></tr>\
									<tr><td>Specialization</td><td>' + data.SPECIALIZATION + '</td></tr>\
									<tr><td>Time at ERAU</td><td>' + data.TIMEATERAU + ' year(s)</td></tr>\
									<tr><td>Time in Program</td><td><em>(No program data)</em></td></tr>\
									<tr><td>Overall Take Rate</td><td>' + data.OVERALLTAKERATE + ' courses per year <span style="float: right;">(class average: ' + data.CLASSAVGTAKERATE + ')</span></td></tr>\
									<tr><td>Program Take Rate</td><td><em>(No program data)</em></td></tr>\
									<tr><td>Campus</td><td>' + data.CAMPUS + '</td></tr>\
									<tr><td>Advisor</td><td>' + advisorName + '</td></tr>\
									<tr><td colspan=2>\
									<div id="chart-holder">\
									<canvas id="chart"></canvas>\
									</div>\
									</td></tr>\
									</table>\
								' );
								} else {
									$( cob_dashboard_modal ).html( '\
									<table class="table table-striped">\
									<tr><td>' + statusLabel + '</td><td>' + status + '</td></tr>\
									<tr><td>GPA</td><td>' + data.CGPU + ' <span style="float: right;">(class average: ' + data.CLASSAVGCGPU + ')</span></td></tr>\
									<tr><td>Degree Plan</td><td>' + data.DEGREEPLAN + '</td></tr>\
									<tr><td>Specialization</td><td>' + data.SPECIALIZATION + '</td></tr>\
									<tr><td>Time at ERAU</td><td>' + data.TIMEATERAU + ' year(s)</td></tr>\
									<tr><td>Time in Program</td><td>' + data.TIMEINMAJOR + ' year(s)</td></tr>\
									<tr><td>Overall Take Rate</td><td>' + data.OVERALLTAKERATE + ' courses per year <span style="float: right;">(class average: ' + data.CLASSAVGTAKERATE + ')</span></td></tr>\
									<tr><td>Program Take Rate</td><td>' + data.MAJORTAKERATE + ' courses per year</td></tr>\
									<tr><td>Campus</td><td>' + data.CAMPUS + '</td></tr>\
									<tr><td>Advisor</td><td>' + advisorName + '</td></tr>\
									<tr><td colspan=2>\
									<div class="ic-Form-control ic-Form-control--radio">\
									<div class="ic-Radio">\
										<input id="chart-overall" type="radio" value="overall" name="chartselector" checked="">\
										<label for="chart-overall" class="ic-Label">Overall Data</label>\
									</div>\
									<div class="ic-Radio">\
										<input id="chart-major" type="radio" value="major" name="chartselector">\
										<label for="chart-major" class="ic-Label">Program Data</label>\
									</div>\
									</div>\
									<div id="chart-holder">\
									<canvas id="chart"></canvas>\
									</div>\
									</td></tr>\
									</table>\
								' );
								}

								dataGlobal = data;

								$( dashboardLink ).find( 'a' ).click(function() {
									$( this ).blur();
									$( cob_dashboard_modal ).dialog({
										title: studentName,
										width: 600,
										resizable: !1,
										close: function(event, ui) 
										{ 
											$(this).dialog('destroy').remove();
										} 
									});
									drawChart("overall");
									
									$("input#chart-overall").click(function() {
										$("#chart").remove();
										$("#chart-holder").append('<canvas id="chart"></canvas>');
										drawChart("overall");
									});
									$("input#chart-major").click(function() {
										$("#chart").remove();
										$("#chart-holder").append('<canvas id="chart"></canvas>');
										drawChart("major");
									});

									event.preventDefault();
									event.stopPropagation();
								});
								
								dashboardLink.slideDown('fast');
							}
							else {
								dashboardLink.html('<small><em>Student Dashboard Data Unavailable</em></small>');
								dashboardLink.slideDown('fast');
							}
							dashboardLoader.slideUp();
							console.log("Dashboard data for student " + studentName + " (" + canvasStudentId + ") for course " + canvasCourseId + " was: " + data.RESULT);
							console.log(data);
						});
					}, 6*1000);
				}, 1500);
			}
		});

		// Include the chart.js script
		var script = document.createElement('script');
		script.setAttribute('src', 'https://cdn.jsdelivr.net/npm/chart.js@2.8.0');
		script.setAttribute('type', 'text/javascript');
		document.documentElement.firstChild.appendChild(script);
	}
    
    // This script resizes iframes somewhat
    $.getScript('https://h5p.org/sites/all/modules/h5p/library/js/h5p-resizer.js');

});

////////////////////////////////////////////////////
// DESIGN TOOLS CONFIG                            //
////////////////////////////////////////////////////
// Copyright (C) 2016  Utah State University
var DT_variables = {
        iframeID: '',
        // Path to the hosted USU Design Tools
        path: 'https://designtools.ciditools.com/',
        templateCourse: '60231',
        // OPTIONAL: Button will be hidden from view until launched using shortcut keys
        hideButton: true,
        // OPTIONAL: Limit tools loading by users role
        limitByRole: false, // set to true to limit to roles in the roleArray
        // adjust roles as needed
        roleArray: [
            'student',
            'teacher',
            'admin'
        ],
        // OPTIONAL: Limit tools to an array of Canvas user IDs
        limitByUser: false, // Change to true to limit by user
        // add users to array (Canvas user ID not SIS user ID)
        userArray: [
            '1234',
            '987654'
        
        ]
    };

// Run the necessary code when a page loads
$(document).ready(function () {
    'use strict';
    // This runs code that looks at each page and determines what controls to create
    $.getScript(DT_variables.path + 'js/master_controls.js', function () {
        console.log('master_controls.js loaded');
    });
});
////////////////////////////////////////////////////
// END DESIGN TOOLS CONFIG                        //
////////////////////////////////////////////////////

/////////////////////////////////////////////////
// Make Multi Tool Visible to Admins           //
/////////////////////////////////////////////////
$(document).ready(function () {
    'use strict';
    var multiToolExternalID = '35108', // external tool id
        // What roles can see the Multi Tool
        multiToolUserRoles = [
            'admin'
        ];
    // Also hidden using CSS, this is to account for currently cached files
    $('.context_external_tool_' + multiToolExternalID).hide();
    $('#nav_edit_tab_id_context_external_tool_' + multiToolExternalID).hide();
    $('#section-tabs a:contains(Multi Tool)').hide();
    // If current user has appropriate role, show the Multi Tool
    $.each(multiToolUserRoles, function (ignore, val) {
        if ($.inArray(val, ENV.current_user_roles) > -1) {
            $('.context_external_tool_' + multiToolExternalID).show();
            $('#nav_edit_tab_id_context_external_tool_' + multiToolExternalID).show();
        }
    });
});
/////////////////////////////////////////////////
/////////////////////////////////////////////////

/////////////////////////////////////////////////
// Rename Syllabus to Summary                  //
/////////////////////////////////////////////////
$(document).ready(function () {
	linkText = $('#section-tabs a[href*="/assignments/syllabus"].syllabus').html();
	if (linkText != null && linkText != undefined) {
		linkText = linkText.replace("Syllabus", "Summary");
	}
	$('#section-tabs a[href*="/assignments/syllabus"].syllabus').html(linkText).attr("title", "Summary");
	// Same change in Navigation > Settings
	if ($('#nav_edit_tab_id_1').length) {
		$('#nav_edit_tab_id_1').html($('#nav_edit_tab_id_1').html().replace(/Syllabus/g, "Summary")).attr("aria-label", "Summary");
	}
	if (window.location.pathname.search("/assignments/syllabus") > 0) {
		var title = window.document.title;
		title = title.replace(/Syllabus/g, "Summary");
		window.document.title = title;
	}
});
/////////////////////////////////////////////////
/////////////////////////////////////////////////
