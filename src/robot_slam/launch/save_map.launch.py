import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():

    map_name = LaunchConfiguration('map_name')
    map_dir  = LaunchConfiguration('map_dir')

    declare_map_name = DeclareLaunchArgument(
        'map_name', default_value='my_map',
        description='Name of the map file (no extension)')

    declare_map_dir = DeclareLaunchArgument(
        'map_dir',
        default_value=os.path.join(os.path.expanduser('~'), 'maps'),
        description='Directory to save the map in')

    # Create maps folder if not exists
    make_dir = ExecuteProcess(
        cmd=['mkdir', '-p', os.path.join(os.path.expanduser('~'), 'maps')],
        output='screen'
    )

    save_map_cmd = ExecuteProcess(
        cmd=[
            'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
            '-f', [map_dir, '/', map_name],
            '--ros-args',
            '-p', 'save_map_timeout:=5.0',
            '-p', 'free_thresh_default:=0.25',
            '-p', 'occupied_thresh_default:=0.65',
        ],
        output='screen'
    )

    return LaunchDescription([
        declare_map_name,
        declare_map_dir,
        make_dir,
        save_map_cmd,
    ])
