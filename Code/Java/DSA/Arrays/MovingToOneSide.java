import java.util.Arrays;

public class MovingToOneSide {

    public static int[] movingToOneSideMethod(int[] array) {

        int read = array.length - 1;
        int write = array.length - 1;

        while (read >= 0) {
            if (array[read] != 0) {
                array[write] = array[read];
                write--;
            }
            read--;
            
        }

        while (write >= 0) {
            array[write] = 0;
            write--;
        }

        return array;
    }

    public static void main(String[] args) {
        int[] array1 = { 12, 0, 3, 5, 0, 7, 65, 0, 8, 4 };
        int[] array2 = { 12, 0, 3, 5, 0, 7, 65, 0, 8, 0, 77888, 0, 0 };

        System.out.println(Arrays.toString(movingToOneSideMethod(array1)));
        System.out.println(Arrays.toString(movingToOneSideMethod(array2)));
    }
}
