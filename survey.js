/* ------------------ BEGIN FUNCTION SECTION */

// Show the survey box when on dashboard page
const showSurvey = function () {
  const { pathname } = window.location;
  let popupMsg = `We\'d love your feedback!<br/>Answer 2 questions?`;
  let QualtricsURL = `https://eraurctle.iad1.qualtrics.com/jfe/form/SV_22VyuADeC2CdcA6?Course=`;
  var browserHTML = ``;
  if (pathname.match(/^\/courses\/\d+$/)) {
    browserHTML = `<div class="container-footnote">`;
    browserHTML += `<button type="button" class="close-button">`;
    browserHTML += `<span class="hidden">Close</span>`;
    browserHTML += `</button>`;

    browserHTML += `<div class="hidden"><svg style="position: absolute; width: 0; height: 0; overflow: hidden" version="1.1" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><title>Eagle icon</title>`;
    browserHTML += `<defs><symbol id="icon-home" viewBox="0 0 1024 1024"><path class="path1" d="M368.89 241.224c13.022 17.167 27.48 33.917 63.281 55.527s63.86 32.206 79.826 33.571c-1.779 2.772-5.005 6.659-23.769 2.811-18.754-3.847-59.072-15.272-59.072-15.272s21.363 12.15 32.031 16.48c10.663 4.318 33.133 12.206 35.562 12.584-1.952 3.096-12.686 6.428-27.705 2.668-27.701-6.928-60.928-23.651-60.928-23.651l56.364 36.362c-2.927 2.964-10.248 1.983-23.335-2.419-13.078-4.41-47.786-22.212-47.786-22.212 6.428 7.401 25.090 24.156 36.279 30.616-3.072 3.273-10.861 0.327-13.484-0.438-8.456-2.5-33.922-14.736-43.157-16.789 1.284 1.764 11.196 10.64 11.957 11.71-5.171 2.113-6.495 2.678-13.29 0.415-10.46-3.488-44.269-29.048-53.764-43.828-16.462-4.779-58.876-29.781-87.149-94.257-4.608 11.136-12.459 41.185-7.93 86.091 0 0-5.014 9.284-11.673 25.533-6.666 16.25-47.422 119.791-39.63 143.269-3.116-1.32-5.339-4.625-7.81-10.866-4.844-12.248-7.833-34.231-1.511-63.039 0 0-22.728 35.458-26.368 69.557-5.411-9.035-8.334-12.428-8.991-28.043-0.614-14.534 2.752-39.9 11.327-57.146 0 0-22.698 32.377-26.666 40.595-3.965 8.216-4.989 11.428-4.989 11.428-2.957-3.442-4.564-8.066-5.157-14.105-0.831-8.338 6.142-51.221 23.413-75.769 0 0-15.004 15.412-24.246 27.764-9.245 12.349-21.047 28.938-21.047 28.938-1.186-5.038-1.118-3.435-1.855-13.816-1.035-14.849 14.174-52.713 31.234-68.796-3.37 1.511-36.48 28.656-39.608 30.849-0.192-6.546 1.702-25.904 17.394-43.078 15.694-17.163 22.214-24.744 22.214-24.744-2.461 1.479-18.009 10.697-19.462 11.713 1.28-4.945 3.981-12.471 5.603-15.535 1.617-3.058 6.569-13.682 20.367-25.611-2.671 0.655-15.472 3.656-19.852 14.418 0.41-7.005 1.393-17.772 13.276-30.923 3.4-8.922 29.6-83.382 55.291-98.351-0.512-1.171-1.536-3.519-1.536-3.519-30.047-10.677-80.846-14.724-111.478-10.956 2.178-2.892 5.093-7.418 8.94-12.884l40.101 3.421-37.291-7.33c2.258-3.077 4.797-6.366 7.62-9.754l36.581 11.005-32.912-15.257c2.57-2.887 5.374-5.817 8.395-8.721l32.531 17.068-28.99-20.375c2.611-2.344 5.376-4.671 8.311-6.933l32.558 18.74-28.546-21.714c3.46-2.473 7.141-4.846 11.059-7.077l30.473 21.056-23.545-24.724c3.379-1.743 6.668-3.082 10.379-4.58 1.869-0.745 27.821 24.606 27.821 24.606s-17.922-27.955-16.341-28.437c2.964-0.918 6.272-1.504 9.431-2.247 1.889-0.433 20.999 28.2 20.999 28.2s-10.483-27.803-10.458-29.876c3.342-0.468 6.366-1.105 9.913-1.361l14.346 28.57 9.15 0.337c0 0 3.785-21.764 5.752-25.853 1.97-4.085 16.966-5.762 23.192-5.452l16.353-9.851c4.094-0.599 8.645-1.942 8.947-4.604 0.304-2.671-4.394-6.154-4.853-10.848-0.445-4.699-3.464-15.469-4.249-19.863-0.789-4.406 8.659-8.278 12.997-9.567l-2.973 11.768 7.936 10.386 28.732-18.032 0.212-8.966c0 0 1.896-0.409 7.046 6.7 7.351 10.135-18.692 23.993-18.692 23.993l17.476-1.873 3.815-9.238c0 0 0.729-1.37 2.77 7.733s-28.183 17.813-34.026 20.366c-5.838 2.56-8.019 7.808-8.019 7.808s2.307 2.36 3.065 3.702c1.178 2.050 0.238 3.344-2.178 6.682-2.429 3.329-1.494 2.644-10.28 6.882-8.792 4.248-15.159 1.517-6.366 17.578 0 0-3.707-9.33-2.491-11.459 1.204-2.127 7.482-3.988 12.632-6.115 5.153-2.108 6.839-3.437 9.23-8.008 4.618-8.818 19.723-12.303 22.516-15.385 7.18-7.943 22.952-19.192 33.214-23.25 8.375-3.303 12.785-21.854 12.785-21.854s-1.825-5.752-4.68-10.704c-2.863-4.95-2.298-7.609-1.421-9.95 0.87-2.344 6.299-5.141 9.803-6.673l-1.396 10.538 9.263 9.793 35.615-10.843c0.824-3.43 1.97-10.241 1.97-10.241s4.043 1.11 8.409 9.754c4.371 8.645-31.408 20.307-36.945 22.394 26.354 6.548 33.935 1.963 33.935 1.963s3.942-4.812 4.592-8.144c0 0 2.219 1.207 3.834 12.889 1.617 11.675-44.437 3.734-51.461 4.071-2.127 1.73-9.671 11.763-9.464 20.664 0.214 8.889-3.912 9.083-9.798 15.691-5.893 6.613-20.894 23.623-22.057 32.007-1.171 8.398-2.652 12.37 8.262 18.079 10.912 5.724 24.454 12.024 24.454 12.024l-0.613-2.542c0 0 48.933 21.76 60.11 17.209 7.288-2.969 6.239-5.099 6.613-7.143 13.375 20.947-15.128 24.74-20.48 26.474 0.526 5.171-1.031 11.173-14.752 13.29-13.731 2.103-35.066 4.373-35.066 4.373l0.897-1.4c0 0-36.445 1.961-42.221 2.454-5.784 0.491-18.092 2.355-18.092 2.355s45.983 17.889 56.403 26.596c10.442 8.693 34.021 33.004 47.039 50.173zM368.554 149.439c1.238-0.784 1.008-1.905 0-3.909l-15.11 4.473c0.666 0 13.88 0.231 15.11-0.563z"></path></symbol></defs></svg></div>`;
    browserHTML += `<svg class="icon icon-home"><use xlink:href="#icon-home"></use></svg>`;
    browserHTML += `<div class="survey-content" id="survey-content-text"><span>${popupMsg}</span>`;
    browserHTML += `<a class="button" id="QualtricsSurvey" href="${QualtricsURL}`;
    browserHTML += window.location.pathname;
    browserHTML += `" target="new">&nbsp;&nbsp; YES &nbsp;&nbsp;</a>`;
    browserHTML += `</div>`;

    setTimeout(function(){
      $('body').append(browserHTML);
    },10000); // 10000ms = 10 seconds

  }

  // Close/hide the browser element
  $('.container-footnote .close-button').click(() => { closeBrowser(); });
};

// Hide survey info when close button is selected
var closeBrowser = function () {
  const container = $('.container-footnote');
  container.addClass('slide-n-hide');
};

$(document).ready(() => { showSurvey(); });
