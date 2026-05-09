import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    pkg_dir = get_package_share_directory('robot_slam')

    use_sim_time   = LaunchConfiguration('use_sim_time')
    map_file_path  = LaunchConfiguration('map_file_path')
    slam_params    = LaunchConfiguration('slam_params_file')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='Use simulation clock if true')

    declare_map_file = DeclareLaunchArgument(
        'map_file_path',
        default_value=os.path.join(os.path.expanduser('~'), 'maps', 'my_map.yaml'),
        description='Full path to saved map yaml file')

    declare_slam_params = DeclareLaunchArgument(
        'slam_params_file',
        default_value=os.path.join(pkg_dir, 'config', 'slam_toolbox_localization_params.yaml'),
        description='Full path to slam toolbox localization params')

    slam_localization_node = Node(
        package='slam_toolbox',
        executable='localization_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            slam_params,
            {'use_sim_time': use_sim_time},
            {'map_file_name': map_file_path},
        ],
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_map_file,
        declare_slam_params,
        slam_localization_node,
    ])
