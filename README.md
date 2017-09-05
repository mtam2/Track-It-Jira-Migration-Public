# Tutorial: How to Setup TrackIT to Jira Migration
## Introduction
TrackIT tickets can now be easily migrated over to a JIRA project via the attached python script along with a configuration file. Current configuration as of August 2017 includes automated migration of Change Requests assigned to user Queue and Support Requests assigned to the business analysts and dev team.
## Prerequisites
*   Have Python 3.6 installed 
    *   Use Anaconda https://www.continuum.io/downloads
*   Have Pymssql installed 
    *       pip install pymssql-2.1.3-cp36-cp36m-win_amd64.whl
*   Confirm that service_jiraapi has access to the database TRACKIT_DATA
## Running the Scripts
1.	Download the attached zip folder and unzip it
1.	Use command prompt and run the following command in the unzipped folder's directory 
    *	python Migration.py support_config.json
1.	Open multiple command prompts to run simultaneous scripts with different config files 

## Change Log
*   7/11/2017 
    *   Migration.py went live with support_config.json and crq_config.json with a restriction of --"and reqdate >= '2017-07-11'"\-- to allow for all technicians to clean out the existing open tickets. 
    *   All TrackIT tickets created from this day forward with the labels ('Ongoing Support','High','Urgent','Critical','Routine') will be automatically closed in TrackIT and moved to JIRA project Support Request Queue
    *   A separate NAME_support_config.json was run once to migrate all of NAME's existing tickets into JIRA
*    7/12/2017 
    *   support_config.json now includes 'Project' in the priority label
    *   Added issue types: Project and Sub-Tasks to SRQ
    *   Migrated existing projects from TrackIT to JIRA
    *   SRQ now has its own workflow copied from CRQ but with an additional post function which auto assigns tickets to the requester
*   7/14/2017 
    *   Error and exception handling was added
    *   Log file name must be specified in the config.json
*   7/31/2017 
    *   Changed TrackIT DB address from **REDACTED** to **REDACTED**
*   8/01/2017 
    *   Due to changing aliases in the active directory to comply with the new Company Identity (CI), a hotfix had to be implemented due to inconsistent columns between the following two tables
    *   **REDACTED**
*   8/14/2017 
    *   Pushed Production Migration v2.0 with PEP8 compliance and due date addition. 
    *   Implemented logging and traceback in more detail.
    *   Added due date field and calculates existing tickets without due dates.
    *   Added comments to provide more readability.
