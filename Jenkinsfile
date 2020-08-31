#!groovy
@Library('jenkins-pipeline-shared') _

slackNotificationConfig = [
    slackChannel: 'team-plateform',
    failureHandler: '@platform-help :sad_parrot:',
    notifyDeployments: false,
    notifyChannelOnSuccess: false
]
beLibraryPipeline([
    project_repo_name: 'docker-remote-aws',
    slackNotificationConfig: slackNotificationConfig
])
